"""Assembles structured JSON context for the LLM from multiple data tools."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis import RedisCache
from app.services.intent_router import Intent
from app.tools.fundamentals import FundamentalsTool
from app.tools.holding import HoldingTool
from app.tools.news import NewsTool
from app.tools.price import PriceTool
from app.tools.technicals import TechnicalsTool

logger = logging.getLogger(__name__)

# Maps intents to the tool keys that should be fetched.
_INTENT_TOOLS: dict[Intent, list[str]] = {
    Intent.STOCK_PRICE: ["price"],
    Intent.STOCK_ANALYSIS: ["price", "technicals", "fundamentals", "news", "shareholding"],
    Intent.WHY_MOVING: ["price", "news", "technicals"],
    Intent.SCREENER: [],  # handled directly by ScreenerTool
    Intent.PORTFOLIO: [],  # handled by portfolio route
    Intent.GENERAL: [],
}

# Simple regex to extract a ticker from a user message
import re

_TICKER_RE = re.compile(
    r"\b([A-Z]{2,20}(?:\.NS|\.BO)?)\b"
    r"|(?:of|for|about|in)\s+([A-Za-z]+)",
    re.IGNORECASE,
)


class ContextBuilder:
    """Fetch and assemble structured context from multiple data sources.

    Cross-validates numeric data points when multiple sources are available
    and attaches confidence and timestamp metadata.
    """

    def __init__(self, db: AsyncSession, redis: RedisCache) -> None:
        self._db = db
        self._redis = redis

    async def build(
        self,
        user_message: str,
        intent: Intent,
        ticker: str | None = None,
    ) -> dict[str, Any]:
        """Assemble context relevant to the classified intent.

        Returns a timestamped dict with source attribution for every data
        block.
        """
        resolved_ticker = ticker or self._extract_ticker(user_message)
        tool_keys = _INTENT_TOOLS.get(intent, [])

        context: dict[str, Any] = {
            "intent": intent.value,
            "ticker": resolved_ticker,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {},
            "confidence": "HIGH",
        }

        if not resolved_ticker or not tool_keys:
            return context

        fetch_tasks = self._schedule_fetches(resolved_ticker, tool_keys)
        results = await asyncio.gather(*fetch_tasks.values(), return_exceptions=True)

        for key, result in zip(fetch_tasks.keys(), results, strict=True):
            if isinstance(result, BaseException):
                logger.warning("Context fetch failed for %s: %s", key, result)
                context["data"][key] = {"error": str(result), "source": key}
            else:
                context["data"][key] = {**result, "source": key}

        # Cross-validate price data if we have both price and technicals
        context["confidence"] = self._cross_validate(context["data"])

        return context

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_ticker(self, message: str) -> str | None:
        """Best-effort ticker extraction from natural language."""
        # Look for NSE/BSE suffixed tickers first
        explicit = re.search(r"\b([A-Z]{2,20})\.(NS|BO)\b", message)
        if explicit:
            return explicit.group(1)

        # Look for uppercase words that look like tickers (2-15 chars)
        candidates = re.findall(r"\b([A-Z]{2,15})\b", message)
        stopwords = {
            "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL",
            "CAN", "HER", "WAS", "ONE", "OUR", "OUT", "HAS", "HIS",
            "HOW", "ITS", "LET", "MAY", "NEW", "NOW", "OLD", "SEE",
            "WAY", "WHO", "BOY", "DID", "GET", "HIM", "RSI", "MACD",
            "WHAT", "WHY", "WITH", "THIS", "THAT", "FROM", "WILL",
            "GIVE", "SHOW", "TELL",
        }
        for c in candidates:
            if c not in stopwords and len(c) >= 3:
                return c

        return None

    def _schedule_fetches(
        self,
        ticker: str,
        tool_keys: list[str],
    ) -> dict[str, Any]:
        """Create async tasks for each required tool fetch."""
        tasks: dict[str, Any] = {}

        tool_map: dict[str, Any] = {
            "price": lambda: PriceTool(db=self._db, redis=self._redis).execute(ticker=ticker),
            "technicals": lambda: TechnicalsTool(db=self._db).execute(ticker=ticker),
            "fundamentals": lambda: FundamentalsTool(db=self._db).execute(ticker=ticker),
            "news": lambda: NewsTool(db=self._db).execute(ticker=ticker, limit=5),
            "shareholding": lambda: HoldingTool(db=self._db).execute(ticker=ticker),
        }

        for key in tool_keys:
            factory = tool_map.get(key)
            if factory:
                tasks[key] = factory()

        return tasks

    @staticmethod
    def _cross_validate(data: dict[str, Any]) -> str:
        """Compare overlapping metrics and return an overall confidence level.

        Returns ``HIGH``, ``MEDIUM``, or ``LOW``.
        """
        price_close = None
        tech_sma_20 = None

        price_block = data.get("price", {})
        tech_block = data.get("technicals", {})

        if isinstance(price_block, dict) and "close" in price_block:
            try:
                price_close = float(price_block["close"])
            except (ValueError, TypeError):
                pass

        if isinstance(tech_block, dict) and "sma_20" in tech_block:
            try:
                tech_sma_20 = float(tech_block["sma_20"])
            except (ValueError, TypeError):
                pass

        if price_close is not None and tech_sma_20 is not None and tech_sma_20 != 0:
            delta_pct = abs(price_close - tech_sma_20) / tech_sma_20 * 100
            if delta_pct > 20:
                return "LOW"
            if delta_pct > 10:
                return "MEDIUM"

        return "HIGH"
