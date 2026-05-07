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

from openai import AsyncOpenAI
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.ticker_ner import build_index
from app.config import get_settings
from app.llm.auth import AuthState, load_state
from app.llm.guardrails import apply_guardrails
from app.llm.intent import classify
from app.llm.prompts import SYSTEM_PROMPT
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
        return {
            "ticker": payload.get("ticker"),
            "available": (payload.get("summary") or {}).get("available"),
            "rsi_14": latest.get("rsi_14"),
            "rsi_zone": (payload.get("summary") or {}).get("rsi_zone"),
            "above_sma50": (payload.get("summary") or {}).get("above_sma50"),
            "above_sma200": (payload.get("summary") or {}).get("above_sma200"),
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
        return {
            "ticker": payload.get("ticker"),
            "available": payload.get("available"),
            "latest_quarter": payload.get("latest_quarter_label"),
            "promoter_pct": latest.get("promoter_pct"),
            "public_pct": latest.get("public_pct"),
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
                tools=TOOL_SPECS,
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
                    model=settings.openai_model_work,
                    temperature=0.2,
                    max_tokens=600,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        *messages[1:-1],   # everything except the just-added assistant turn
                    ],
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
                result = await dispatch(name, args, session=session, redis=redis)
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
