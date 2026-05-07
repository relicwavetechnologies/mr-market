"""PriceTool — fetch live / cached stock price data."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis import RedisCache
from app.tools.base import BaseTool
from mr_market_shared.db.models import Price

logger = logging.getLogger(__name__)

_CACHE_KEY_PREFIX = "price:"
_CACHE_TTL_SECONDS = 30  # live prices are very short-lived


class PriceTool(BaseTool):
    """Fetch the latest price for a ticker.

    Resolution order:
      1. Redis cache (``price:{ticker}``).
      2. Database (most recent row in ``prices`` table).
      3. yfinance API (fallback — not available in prod scraper flow).
    """

    name = "get_live_price"
    description = (
        "Get the current / latest price for an Indian stock ticker. "
        "Returns OHLCV data with timestamp."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "NSE ticker symbol, e.g. RELIANCE, TCS, INFY",
            },
        },
        "required": ["ticker"],
    }

    def __init__(self, db: AsyncSession, redis: RedisCache) -> None:
        self._db = db
        self._redis = redis

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        ticker: str = kwargs["ticker"].upper().strip()

        # 1. Try Redis cache first
        cached = await self._redis.get(f"{_CACHE_KEY_PREFIX}{ticker}")
        if cached is not None:
            logger.debug("Cache hit for %s", ticker)
            return {**cached, "source": "cache"}

        # 2. Fall back to database
        result = await self._fetch_from_db(ticker)
        if result:
            await self._redis.set(
                f"{_CACHE_KEY_PREFIX}{ticker}",
                result,
                ttl=_CACHE_TTL_SECONDS,
            )
            return {**result, "source": "database"}

        # 3. Fallback to yfinance (development / gap-fill only)
        result = await self._fetch_from_yfinance(ticker)
        if result:
            await self._redis.set(
                f"{_CACHE_KEY_PREFIX}{ticker}",
                result,
                ttl=_CACHE_TTL_SECONDS,
            )
            return {**result, "source": "yfinance"}

        return {"error": f"No price data found for {ticker}", "ticker": ticker}

    async def _fetch_from_db(self, ticker: str) -> dict[str, Any] | None:
        """Load the most recent price row from the database."""
        stmt = (
            select(Price)
            .where(Price.ticker == ticker)
            .order_by(Price.timestamp.desc())
            .limit(1)
        )
        row = (await self._db.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None

        return {
            "ticker": row.ticker,
            "open": float(row.open) if row.open else None,
            "high": float(row.high) if row.high else None,
            "low": float(row.low) if row.low else None,
            "close": float(row.close) if row.close else None,
            "volume": row.volume,
            "timestamp": row.timestamp.isoformat(),
        }

    @staticmethod
    async def _fetch_from_yfinance(ticker: str) -> dict[str, Any] | None:
        """Best-effort yfinance lookup (runs in thread executor)."""
        import asyncio

        def _sync_fetch() -> dict[str, Any] | None:
            try:
                import yfinance as yf  # type: ignore[import-untyped]
            except ImportError:
                logger.warning("yfinance not installed — cannot fetch %s", ticker)
                return None

            nse_ticker = f"{ticker}.NS"
            stock = yf.Ticker(nse_ticker)
            hist = stock.history(period="1d")
            if hist.empty:
                return None

            latest = hist.iloc[-1]
            return {
                "ticker": ticker,
                "open": round(float(latest["Open"]), 2),
                "high": round(float(latest["High"]), 2),
                "low": round(float(latest["Low"]), 2),
                "close": round(float(latest["Close"]), 2),
                "volume": int(latest["Volume"]),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        return await asyncio.get_event_loop().run_in_executor(None, _sync_fetch)
