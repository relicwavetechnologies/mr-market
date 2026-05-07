"""LLM tool catalog (OpenAI tool-calling shape) + dispatch.

Each tool corresponds 1:1 to a real backend service that already exists. Tool
results are JSON — never prose — so the verifier (D5) can match numeric claims
in the LLM's output against the source-truth set.
"""

from __future__ import annotations

import json
from typing import Any

from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import desc, select

from app.data.info_service import get_info
from app.data.news_service import get_news_for_ticker
from app.data.quote_service import get_quote
from app.db.models.technicals import Technicals


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_quote",
            "description": (
                "Get the current cross-validated price for one Indian stock "
                "(NSE/BSE). Returns the median price across yfinance, NSE, "
                "Screener, and Moneycontrol with a HIGH/MED/LOW confidence label "
                "based on inter-source spread. Use this whenever the user asks "
                "for a price, change, or day range."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "NSE ticker symbol (e.g., RELIANCE, TCS, HDFCBANK).",
                    },
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": (
                "Get recent headlines for an Indian stock with sentiment scores. "
                "Use this for 'why is X falling' or 'what's the news on X' questions. "
                "Sources are public RSS feeds (Pulse, Moneycontrol, ET Markets)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "NSE ticker symbol"},
                    "hours": {
                        "type": "integer",
                        "description": "Lookback window in hours (default 24, max 72).",
                        "minimum": 1,
                        "maximum": 72,
                    },
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_technicals",
            "description": (
                "Get the latest technical-indicator snapshot for an Indian stock: "
                "RSI-14, MACD(12,26,9), Bollinger(20,2), SMA-20/50/200, EMA-12/26, "
                "ATR-14, 20-day average volume. Computed nightly off our EOD "
                "bhavcopy ingest. Use this for questions about momentum, trend "
                "(price vs SMA-50/200), volatility (ATR / Bollinger width), or "
                "stop-loss observations (ATR is the standard input). Returns "
                "factual indicator values plus a small qualitative summary "
                "(rsi_zone, bb_position) — no recommendations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "NSE ticker symbol"},
                    "days": {
                        "type": "integer",
                        "description": "How many recent bars to include (default 1, max 60).",
                        "minimum": 1,
                        "maximum": 60,
                    },
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_company_info",
            "description": (
                "Get fundamental info about an Indian stock: sector, industry, market "
                "cap, P/E (trailing + forward), price-to-book, dividend yield, beta, "
                "52-week range. Pulled from yfinance and Screener.in side-by-side."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "NSE ticker symbol"},
                },
                "required": ["ticker"],
            },
        },
    },
]


async def dispatch(
    name: str,
    args: dict[str, Any],
    *,
    session: AsyncSession,
    redis: aioredis.Redis,
) -> dict[str, Any]:
    """Run one tool by name. Always returns a JSON-serialisable dict."""
    if name == "get_quote":
        return await get_quote(str(args["ticker"]), redis, session)
    if name == "get_news":
        hours = int(args.get("hours") or 24)
        return await get_news_for_ticker(session, redis, str(args["ticker"]), hours=hours)
    if name == "get_company_info":
        return await get_info(session, str(args["ticker"]))
    if name == "get_technicals":
        return await _get_technicals_payload(
            session, str(args["ticker"]), days=int(args.get("days") or 1)
        )
    return {"error": f"unknown tool: {name}"}


async def _get_technicals_payload(
    session: AsyncSession, ticker: str, *, days: int
) -> dict[str, Any]:
    """Read the most recent indicator rows; mirror /technicals/{ticker} shape."""
    sym = ticker.upper().strip()
    rows = (
        await session.execute(
            select(Technicals)
            .where(Technicals.ticker == sym)
            .order_by(desc(Technicals.ts))
            .limit(max(1, min(days, 60)))
        )
    ).scalars().all()
    if not rows:
        return {"ticker": sym, "available": False, "note": "no technicals computed yet"}

    def _f(d):
        return str(d) if d is not None else None

    latest = rows[0]
    series = [
        {
            "ts": r.ts.isoformat() if r.ts else None,
            "close": _f(r.close),
            "rsi_14": _f(r.rsi_14),
            "macd": _f(r.macd),
            "macd_signal": _f(r.macd_signal),
            "sma_50": _f(r.sma_50),
            "sma_200": _f(r.sma_200),
            "atr_14": _f(r.atr_14),
        }
        for r in rows
    ]
    summary: dict[str, Any] = {"available": True}
    if latest.rsi_14 is not None:
        v = float(latest.rsi_14)
        summary["rsi_zone"] = (
            "overbought" if v >= 70 else "oversold" if v <= 30 else "neutral"
        )
    if latest.close is not None and latest.sma_50 is not None:
        summary["above_sma50"] = float(latest.close) > float(latest.sma_50)
    if latest.close is not None and latest.sma_200 is not None:
        summary["above_sma200"] = float(latest.close) > float(latest.sma_200)
    if latest.macd is not None and latest.macd_signal is not None:
        summary["macd_above_signal"] = float(latest.macd) > float(latest.macd_signal)

    return {
        "ticker": sym,
        "as_of": latest.ts.isoformat() if latest.ts else None,
        "summary": summary,
        "latest": {
            "close": _f(latest.close),
            "rsi_14": _f(latest.rsi_14),
            "macd": _f(latest.macd),
            "macd_signal": _f(latest.macd_signal),
            "macd_hist": _f(latest.macd_hist),
            "bb_upper": _f(latest.bb_upper),
            "bb_middle": _f(latest.bb_middle),
            "bb_lower": _f(latest.bb_lower),
            "sma_20": _f(latest.sma_20),
            "sma_50": _f(latest.sma_50),
            "sma_200": _f(latest.sma_200),
            "ema_12": _f(latest.ema_12),
            "ema_26": _f(latest.ema_26),
            "atr_14": _f(latest.atr_14),
            "vol_avg_20": latest.vol_avg_20,
        },
        "series": series,
    }


def tool_result_to_json_string(payload: dict[str, Any]) -> str:
    """Compact JSON string that we send back as the `tool` message content."""
    return json.dumps(payload, default=str, ensure_ascii=False)
