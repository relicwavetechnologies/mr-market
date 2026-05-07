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

from app.data.info_service import get_info
from app.data.news_service import get_news_for_ticker
from app.data.quote_service import get_quote


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
    return {"error": f"unknown tool: {name}"}


def tool_result_to_json_string(payload: dict[str, Any]) -> str:
    """Compact JSON string that we send back as the `tool` message content."""
    return json.dumps(payload, default=str, ensure_ascii=False)
