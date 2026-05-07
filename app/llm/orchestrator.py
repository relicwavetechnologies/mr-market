"""OpenAI tool-calling orchestrator + SSE-friendly streaming.

Yields plain strings (deltas) for the answer text, plus structured envelope
events (`tool_call`, `tool_result`, `done`, `error`) so the frontend can
render the "see how the sausage is made" admin trail.

The orchestrator returns an async generator of dicts:
    {"type": "delta",        "text": "..."}
    {"type": "tool_call",    "name": "get_quote",   "args": {...}}
    {"type": "tool_result",  "name": "get_quote",   "ms": 412, "summary": {...}}
    {"type": "intent",       "intent": "quote", "ticker": "RELIANCE"}
    {"type": "done",         "message": "<full text>", "tool_results": {...}}
    {"type": "error",        "message": "..."}
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import structlog
from openai import AsyncOpenAI
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.ticker_ner import build_index
from app.config import get_settings
from app.llm.auth import AuthState, effective_models, load_state
from app.llm.codex_client import CodexOpenAIClient
from app.llm.guardrails import apply_guardrails
from app.llm.intent import classify
from app.llm.memory import (
    MemoryHit,
    build_memory_block,
    build_memory_recall_answer,
    looks_like_memory_recall_query,
    memory_service,
)
from app.llm.prompts import SYSTEM_PROMPT
from app.llm.tool_routing import filter_tool_specs
from app.llm.tools import TOOL_SPECS, dispatch, tool_result_to_json_string

logger = logging.getLogger(__name__)
event_log = structlog.get_logger(__name__)

MAX_TOOL_ROUNDS = 3
MEMORY_TOOL_NAME = "remember_fact"


def _client(auth: AuthState) -> Any:
    if auth.source in {"codex_oauth", "codex_cli"}:
        return CodexOpenAIClient(auth.api_key or "")
    return AsyncOpenAI(api_key=auth.api_key)


def _summarise(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Tiny preview of a tool result for the frontend admin panel."""
    if name == "get_quote":
        srcs = [s["name"] for s in (payload.get("sources") or [])]
        return {
            "ticker": payload.get("ticker"),
            "price": payload.get("price"),
            "confidence": payload.get("confidence"),
            "spread_pct": payload.get("spread_pct"),
            "ok_sources": srcs,
            "failed_sources": list((payload.get("failed_sources") or {}).keys()),
            "cache": payload.get("cache"),
        }
    if name == "get_news":
        return {
            "ticker": payload.get("ticker"),
            "count": payload.get("count"),
            "average_sentiment": payload.get("average_sentiment"),
            "label_counts": payload.get("label_counts"),
        }
    if name == "get_company_info":
        return {
            "ticker": payload.get("ticker"),
            "yfinance_ok": payload.get("yfinance") is not None,
            "screener_ok": payload.get("screener") is not None,
        }
    if name == "get_technicals":
        latest = payload.get("latest") or {}
        summary = payload.get("summary") or {}
        return {
            "ticker": payload.get("ticker"),
            "available": summary.get("available"),
            "as_of": payload.get("as_of"),
            "close": latest.get("close"),
            "rsi_14": latest.get("rsi_14"),
            "rsi_zone": summary.get("rsi_zone"),
            "macd": latest.get("macd"),
            "macd_signal": latest.get("macd_signal"),
            "macd_above_signal": summary.get("macd_above_signal"),
            "sma_50": latest.get("sma_50"),
            "sma_200": latest.get("sma_200"),
            "above_sma50": summary.get("above_sma50"),
            "above_sma200": summary.get("above_sma200"),
            "atr_14": latest.get("atr_14"),
        }
    if name == "get_levels":
        return {
            "ticker": payload.get("ticker"),
            "available": payload.get("available"),
            "n_resistance": len(payload.get("resistance") or []),
            "n_support": len(payload.get("support") or []),
            "fib_direction": (payload.get("fibonacci") or {}).get("direction"),
        }
    if name == "get_holding":
        latest = payload.get("latest") or {}
        pledge = payload.get("pledge") or {}
        return {
            "ticker": payload.get("ticker"),
            "available": payload.get("available"),
            "latest_quarter": payload.get("latest_quarter_label"),
            "promoter_pct": latest.get("promoter_pct"),
            "public_pct": latest.get("public_pct"),
            "employee_trust_pct": latest.get("employee_trust_pct"),
            "pledged_pct": latest.get("pledged_pct") or pledge.get("pledged_pct"),
            "pledge_risk_band": latest.get("pledge_risk_band") or pledge.get("risk_band"),
            "xbrl_url": payload.get("xbrl_url"),
            "n_quarters": len(payload.get("series") or []),
        }
    if name == "get_deals":
        return {
            "ticker": payload.get("ticker"),
            "available": payload.get("available"),
            "kind": payload.get("kind"),
            "n_deals": payload.get("n_deals"),
            "n_buys": payload.get("n_buys"),
            "n_sells": payload.get("n_sells"),
            "net_qty": payload.get("net_qty"),
        }
    if name == "get_research":
        hits = payload.get("hits") or []
        # Top-3 citations for the UI card. Each is small (no chunk text) so
        # the SSE summary stays compact.
        top_hits = [
            {
                "document_title": h.get("document_title"),
                "document_fy": h.get("document_fy"),
                "page": h.get("page"),
                "score": h.get("score"),
            }
            for h in hits[:3]
        ]
        # De-duplicated (title, fy) pairs across all hits, for the
        # "documents consulted" footer line.
        documents = sorted(
            {(h.get("document_title"), h.get("document_fy")) for h in hits}
        )
        return {
            "ticker": payload.get("ticker"),
            "available": payload.get("available"),
            "n_hits": payload.get("n_hits"),
            "top_score": (max((h.get("score") or 0) for h in hits) if hits else None),
            "top_hits": top_hits,
            "documents": documents,
        }
    if name == "remember_fact":
        return {
            "stored": payload.get("stored"),
            "fact": payload.get("fact"),
            "error": payload.get("error"),
        }
    return {"raw_keys": list(payload.keys())}


def _tool_specs_for_turn(*, memory_available: bool) -> list[dict[str, Any]]:
    if memory_available:
        return TOOL_SPECS
    return [
        spec
        for spec in TOOL_SPECS
        if spec.get("function", {}).get("name") != MEMORY_TOOL_NAME
    ]


async def run_chat(
    user_message: str,
    *,
    session: AsyncSession,
    redis: aioredis.Redis,
    user_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    settings = get_settings()
    auth: AuthState = await load_state(redis)
    models = effective_models(auth, settings)
    if not auth.configured or auth.api_key is None:
        yield {
            "type": "error",
            "message": (
                "Codex is not connected. Connect OpenAI in the header to use "
                "GPT-5.4 mini. To use GPT-4o mini fallback, set the backend "
                "OPENAI_API_KEY or paste the key in the header fallback field."
            ),
        }
        return

    client = _client(auth)
    yield {
        "type": "auth",
        "source": auth.source,
        "model": models.work,
        "using_fallback": models.using_fallback,
        "message": models.fallback_reason,
    }

    handled = await _handle_memory_command(
        user_message,
        user_id=user_id,
        api_key=auth.api_key,
        redis=redis,
    )
    if handled is not None:
        for chunk in _chunk(handled, size=20):
            yield {"type": "delta", "text": chunk}
        yield {
            "type": "done",
            "message": handled,
            "tool_results": {},
            "blocked": False,
        }
        return

    memory_query = looks_like_memory_recall_query(user_message)
    memory_reason = memory_service.availability_reason(
        settings,
        api_key=auth.api_key,
        user_id=user_id,
    )
    memory_summary: dict[str, Any] | None = None
    recalled_memories: list[MemoryHit] = []

    if memory_reason is None and user_id is not None:
        memory_summary = await memory_service.get_summary(
            user_id,
            redis=redis,
            api_key=auth.api_key,
        )
        if memory_query:
            recalled_memories = await memory_service.search(
                user_id,
                user_message,
                api_key=auth.api_key,
                redis=redis,
                use_cache=True,
                k=settings.mem0_max_inject,
                min_score=settings.mem0_min_score,
            )

    memory_status = _memory_status_payload(
        query_is_memory=memory_query,
        summary=memory_summary,
        hits=recalled_memories,
        unavailable_reason=memory_reason,
    )
    if memory_status is not None:
        yield {"type": "memory_status", **memory_status}

    if recalled_memories:
        yield {
            "type": "memory",
            "count": len(recalled_memories),
            "facts": [hit.text for hit in recalled_memories],
        }

    if memory_query:
        direct = build_memory_recall_answer(
            memory_summary,
            recalled_memories,
            unavailable_reason=memory_reason,
        )
        for chunk in _chunk(direct, size=20):
            yield {"type": "delta", "text": chunk}
        yield {
            "type": "done",
            "message": direct,
            "tool_results": {},
            "blocked": False,
        }
        return

    # Build ticker index once for the disclaimer injector. Cheap (50 rows).
    try:
        ticker_index = await build_index(session)
    except Exception as e:  # noqa: BLE001
        logger.warning("ticker_index build failed: %s", e)
        ticker_index = None

    # --- Intent + ticker pre-extraction (cheap, single Haiku-style call) -------
    intent_info = await classify(client, user_message, model=models.router)
    yield {
        "type": "intent",
        "intent": intent_info.get("intent"),
        "ticker": intent_info.get("ticker"),
    }

    # --- Off-topic / nonsense short-circuit ------------------------------------
    # In Phase-2 internal-tool mode the router only emits "refuse" for genuine
    # off-topic / non-financial questions ("what's the weather?"). Advisory
    # asks (buy/sell/target/SL) get routed to "advisory" and answered.
    if intent_info.get("intent") == "refuse":
        msg = (
            "I'm an internal stock-market analyst tool — that question is "
            "outside my scope. I can give you analyst-style views on Indian "
            "equities (price, news, fundamentals, technicals, levels, "
            "shareholding, institutional flows). What would you like?"
        )
        for chunk in _chunk(msg, size=20):
            yield {"type": "delta", "text": chunk}
        yield {
            "type": "guardrail",
            "overridden": False,
            "blocklist_hits": [],
            "claim_mismatches": [],
            "disclaimer_injected": False,
            "router_short_circuit": True,
        }
        yield {
            "type": "done",
            "message": msg,
            "tool_results": {},
            "blocked": True,
        }
        return

    # --- Main tool-calling loop -----------------------------------------------
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if memory_summary is not None or recalled_memories:
        messages.append(
            {
                "role": "system",
                "content": build_memory_block(memory_summary, recalled_memories),
            }
        )
    memory_available = memory_reason is None and user_id is not None
    tool_specs = _tool_specs_for_turn(memory_available=memory_available)
    if not memory_available:
        event_log.info(
            "remember_fact_tool_disabled",
            reason=memory_reason or "anonymous",
            signed_in=user_id is not None,
        )
        messages.append(
            {
                "role": "system",
                "content": (
                    "Durable memory saving is unavailable for this turn. If the user "
                    "states a preference, acknowledge it for the current conversation "
                    "only and do not claim it was saved."
                ),
            }
        )
    messages.append({"role": "user", "content": user_message})

    # Narrow the tool catalog based on the router's intent — fewer tools
    # surfaced to the workhorse means fewer over-fires per turn (D8).
    active_tools = filter_tool_specs(tool_specs, intent=intent_info.get("intent"))

    final_text_parts: list[str] = []
    tool_results: dict[str, dict[str, Any]] = {}

    for round_ix in range(MAX_TOOL_ROUNDS):
        # First we make a non-streamed call to discover tool calls; once the
        # model decides "no more tools" we re-call with streaming for the
        # final answer. Mixing streaming + tool-calling on Chat Completions
        # adds chunk-assembly complexity we don't need for a demo.
        try:
            resp = await client.chat.completions.create(
                model=models.work,
                temperature=0.2,
                max_tokens=600,
                tools=active_tools,
                tool_choice="auto",
                messages=messages,
            )
        except Exception as e:  # noqa: BLE001
            yield {"type": "error", "message": f"OpenAI error: {e!s}"}
            return

        choice = resp.choices[0]
        message = choice.message
        tool_calls = list(message.tool_calls or [])

        if not tool_calls:
            # No (more) tools needed — stream the final answer.
            messages.append({"role": "assistant", "content": message.content or ""})
            try:
                stream = await client.chat.completions.create(
                    model=models.work,
                    temperature=0.2,
                    max_tokens=600,
                    messages=messages[
                        :-1
                    ],  # everything except the just-added assistant turn
                    stream=True,
                )
            except Exception as e:  # noqa: BLE001
                yield {"type": "error", "message": f"OpenAI stream error: {e!s}"}
                return

            async for ev in stream:
                delta = ev.choices[0].delta.content if ev.choices else None
                if delta:
                    final_text_parts.append(delta)
                    yield {"type": "delta", "text": delta}

            buffered = "".join(final_text_parts)
            guarded = apply_guardrails(
                buffered,
                tool_results=tool_results,
                ticker_index=ticker_index,
                mode=settings.guardrail_mode,
            )
            yield {
                "type": "guardrail",
                **guarded.to_audit_dict(),
                "mode": settings.guardrail_mode,
            }
            yield {
                "type": "done",
                "message": guarded.final_text,
                "tool_results": tool_results,
                "blocked": guarded.overridden,
            }
            return

        # Run all requested tools.
        messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = _safe_json(tc.function.arguments)
            except Exception as e:  # noqa: BLE001
                args = {"_parse_error": str(e)}
            yield {"type": "tool_call", "name": name, "args": args}

            t0 = time.perf_counter()
            try:
                result = await dispatch(
                    name, args, session=session, redis=redis, user_id=user_id
                )
            except Exception as e:  # noqa: BLE001
                result = {"error": str(e)}
            duration_ms = int((time.perf_counter() - t0) * 1000)
            tool_results.setdefault(name, []).append({"args": args, "result": result})
            yield {
                "type": "tool_result",
                "name": name,
                "ms": duration_ms,
                "summary": _summarise(name, result),
            }

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result_to_json_string(result),
                }
            )

            if name == "remember_fact":
                if result.get("stored") is True:
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                "The memory save succeeded. Briefly confirm the saved preference "
                                "without mentioning hidden tools."
                            ),
                        }
                    )
                else:
                    error = str(result.get("error") or "memory save failed")
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                "The memory save failed. You must tell the user it could not be "
                                f"saved. Reason: {error}. Do not imply success."
                            ),
                        }
                    )
        # Loop continues: model may want more tools or now compose the final answer.

    # If we exhausted tool rounds without a final answer, ask once more without tools.
    try:
        stream = await client.chat.completions.create(
            model=models.work,
            temperature=0.2,
            max_tokens=600,
            messages=messages,
            stream=True,
        )
    except Exception as e:  # noqa: BLE001
        yield {"type": "error", "message": f"OpenAI stream error: {e!s}"}
        return

    async for ev in stream:
        delta = ev.choices[0].delta.content if ev.choices else None
        if delta:
            final_text_parts.append(delta)
            yield {"type": "delta", "text": delta}

    buffered = "".join(final_text_parts)
    guarded = apply_guardrails(
        buffered,
        tool_results=tool_results,
        ticker_index=ticker_index,
        mode=settings.guardrail_mode,
    )
    yield {
        "type": "guardrail",
        **guarded.to_audit_dict(),
        "mode": settings.guardrail_mode,
    }
    yield {
        "type": "done",
        "message": guarded.final_text,
        "tool_results": tool_results,
        "blocked": guarded.overridden,
    }


def _safe_json(s: str) -> dict[str, Any]:
    import json as _json

    if not s:
        return {}
    try:
        out = _json.loads(s)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def _chunk(text: str, *, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


async def _handle_memory_command(
    user_message: str,
    *,
    user_id: str | None,
    api_key: str | None,
    redis: aioredis.Redis,
) -> str | None:
    text = user_message.strip()
    lowered = text.lower()
    if not lowered.startswith(("/remember", "/forget", "/memories")):
        return None

    if not user_id:
        return "Sign in to use Midas memory commands."
    settings = get_settings()
    if not settings.mem0_enabled:
        return "Midas memory is disabled in this environment."

    if lowered.startswith("/remember"):
        fact = text[len("/remember") :].strip()
        if not fact:
            return "Usage: /remember <durable preference or fact>"
        saved = await memory_service.add_explicit(
            user_id, fact, api_key=api_key, redis=redis
        )
        if saved is None:
            return "I could not save that memory right now."
        return f"Got it - I'll remember: {fact}"

    if lowered.startswith("/forget"):
        query = text[len("/forget") :].strip()
        if not query:
            return "Usage: /forget <memory to remove>"
        hits = await memory_service.search(
            user_id, query, api_key=api_key, k=1, min_score=0.0
        )
        if not hits:
            return "I could not find a matching memory to forget."
        deleted = await memory_service.delete(
            user_id, hits[0].id, api_key=api_key, redis=redis
        )
        if not deleted:
            return "I found a matching memory, but could not delete it right now."
        return f"Done - I've forgotten: {hits[0].text}"

    memories: list[MemoryHit] = await memory_service.list(
        user_id, api_key=api_key, limit=50
    )
    if not memories:
        return "No saved Midas memories yet."
    rendered = "\n".join(f"- {hit.text}" for hit in memories)
    return f"Saved Midas memories:\n{rendered}"


def _memory_status_payload(
    *,
    query_is_memory: bool,
    summary: dict[str, Any] | None,
    hits: list[MemoryHit],
    unavailable_reason: str | None,
) -> dict[str, Any] | None:
    if unavailable_reason is not None:
        if query_is_memory:
            return {
                "status": "unavailable",
                "reason": unavailable_reason,
                "source": "none",
                "summary_version": None,
            }
        return None

    used_summary = summary is not None
    used_search = bool(hits)
    if not used_summary and not used_search and not query_is_memory:
        return None

    if used_summary and used_search:
        source = "summary+search"
    elif used_summary:
        source = "summary"
    elif used_search:
        source = "search"
    else:
        source = "none"

    return {
        "status": "used" if (used_summary or used_search) else "miss",
        "reason": None if (used_summary or used_search) else "no_relevant_memory",
        "source": source,
        "summary_version": int((summary or {}).get("version") or 0)
        if used_summary
        else None,
        "facts_count": len((summary or {}).get("facts") or []),
        "hits_count": len(hits),
    }
