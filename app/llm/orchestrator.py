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

Latency notes (P2-D11)
----------------------
* When the workhorse returns content with no further tool_calls, we
  reuse that content directly as pseudo-deltas instead of re-calling
  OpenAI with `stream=True` to regenerate the same answer. Saves 1
  full LLM round trip on every "final answer" turn (~1.5-3 s).
* When the workhorse asks for ≥2 tools in the same round, we run
  them concurrently via `asyncio.gather`. Saves N×(tool latency)
  on multi-tool turns; a 3-tool round drops from sum to max.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.ticker_ner import build_index
from app.config import get_settings
from app.llm.auth import AuthState, load_state
from app.llm.guardrails import apply_guardrails
from app.llm.intent import classify
from app.llm.prompts import SYSTEM_PROMPT
from app.llm.tool_routing import filter_tool_specs
from app.llm.tools import TOOL_SPECS, dispatch, tool_result_to_json_string

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3


def _client(api_key: str) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key)


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
        series = payload.get("series") or []
        # Trim to the last 5 bars for the card's expand-to-history view.
        compact_series = [
            {
                "ts": s.get("ts"),
                "close": s.get("close"),
                "rsi_14": s.get("rsi_14"),
            }
            for s in series[:5]
        ]
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
            "series": compact_series,
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
        series = payload.get("series") or []
        # Last 4 quarters for the expand-to-history view.
        compact_series = [
            {
                "quarter_label": s.get("quarter_label"),
                "promoter_pct": s.get("promoter_pct"),
                "public_pct": s.get("public_pct"),
            }
            for s in series[:4]
        ]
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
            "n_quarters": len(series),
            "series": compact_series,
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
    return {"raw_keys": list(payload.keys())}


async def run_chat(
    user_message: str,
    *,
    session: AsyncSession,
    redis: aioredis.Redis,
) -> AsyncIterator[dict[str, Any]]:
    settings = get_settings()
    auth: AuthState = await load_state(redis)
    if not auth.configured or auth.api_key is None:
        yield {
            "type": "error",
            "message": (
                "No OpenAI credential found. Either set OPENAI_API_KEY in .env, "
                "run `codex login` (we read ~/.codex/auth.json), or POST your key "
                "to /auth/openai/key."
            ),
        }
        return

    client = _client(auth.api_key)
    yield {"type": "auth", "source": auth.source}

    # Build ticker index once for the disclaimer injector. Cheap (50 rows).
    try:
        ticker_index = await build_index(session)
    except Exception as e:  # noqa: BLE001
        logger.warning("ticker_index build failed: %s", e)
        ticker_index = None

    # --- Intent + ticker pre-extraction (cheap, single Haiku-style call) -------
    intent_info = await classify(client, user_message)
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
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    # Narrow the tool catalog based on the router's intent — fewer tools
    # surfaced to the workhorse means fewer over-fires per turn (D8).
    active_tools = filter_tool_specs(
        TOOL_SPECS, intent=intent_info.get("intent")
    )

    final_text_parts: list[str] = []
    tool_results: dict[str, dict[str, Any]] = {}

    for round_ix in range(MAX_TOOL_ROUNDS):
        # First we make a non-streamed call to discover tool calls; once the
        # model decides "no more tools" we re-call with streaming for the
        # final answer. Mixing streaming + tool-calling on Chat Completions
        # adds chunk-assembly complexity we don't need for a demo.
        try:
            resp = await client.chat.completions.create(
                model=settings.openai_model_work,
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
            # No (more) tools needed. The workhorse already produced the
            # final answer in `message.content` on this same call — emit it
            # as pseudo-deltas instead of re-calling OpenAI with stream=True
            # to regenerate the same text. Saves ~1.5-3 s per "answered"
            # turn at zero quality cost.
            buffered = message.content or ""
            for chunk in _chunk(buffered, size=24):
                final_text_parts.append(chunk)
                yield {"type": "delta", "text": chunk}

            guarded = apply_guardrails(
                buffered,
                tool_results=tool_results,
                ticker_index=ticker_index,
                mode=settings.guardrail_mode,
            )
            yield {"type": "guardrail", **guarded.to_audit_dict(), "mode": settings.guardrail_mode}
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

        # Pre-emit tool_call envelopes (before dispatch) so the frontend
        # can render the "running" pills as soon as the orchestrator knows
        # what's coming.
        prepared: list[tuple[Any, str, dict[str, Any]]] = []
        for tc in tool_calls:
            name = tc.function.name
            try:
                args = _safe_json(tc.function.arguments)
            except Exception as e:  # noqa: BLE001
                args = {"_parse_error": str(e)}
            yield {"type": "tool_call", "name": name, "args": args}
            prepared.append((tc, name, args))

        # Run all requested tools concurrently. The DB session is async-safe
        # against parallel SELECTs; each tool's HTTP scrape uses its own
        # short-lived AsyncClient. A 3-tool round goes from sum(latencies)
        # to max(latencies).
        async def _run_one(name: str, args: dict[str, Any]) -> tuple[dict[str, Any], int]:
            t0 = time.perf_counter()
            try:
                result = await dispatch(name, args, session=session, redis=redis)
            except Exception as e:  # noqa: BLE001
                result = {"error": str(e)}
            return result, int((time.perf_counter() - t0) * 1000)

        results = await asyncio.gather(
            *[_run_one(name, args) for _, name, args in prepared]
        )

        for (tc, name, args), (result, duration_ms) in zip(prepared, results):
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
        # Loop continues: model may want more tools or now compose the final answer.

    # If we exhausted tool rounds without a final answer, ask once more without tools.
    try:
        stream = await client.chat.completions.create(
            model=settings.openai_model_work,
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
    yield {"type": "guardrail", **guarded.to_audit_dict(), "mode": settings.guardrail_mode}
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
