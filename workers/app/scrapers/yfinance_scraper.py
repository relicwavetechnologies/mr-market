"""yfinance scraper — historical OHLCV, live quotes, and basic fundamentals.

Wraps the ``yfinance`` library to fetch historical daily candles, live/delayed
price quotes, and basic fundamental data for cross-validation with Screener.in.

Rate limit: 60 req/min (1 req/s). Yahoo is lenient but throttles above this.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
import yfinance as yf  # type: ignore[import-untyped]

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class YFinanceScraper(BaseScraper):
    """Wraps yfinance for OHLCV data, quotes, and fundamental cross-validation."""

    name = "yfinance"
    source_url = "https://finance.yahoo.com"
    rate_limit = 1.0  # 60 req/min

    # ------------------------------------------------------------------
    # Historical OHLCV data
    # ------------------------------------------------------------------

    async def fetch_ohlcv(
        self,
        ticker: str,
        period_days: int = 365,
        interval: str = "1d",
    ) -> list[dict[str, Any]]:
        """Fetch daily OHLCV candles for *ticker*.

        Parameters
        ----------
        ticker:
            NSE ticker symbol (e.g. ``"RELIANCE"``). ``.NS`` suffix is
            appended automatically.
        period_days:
            Number of days of history to fetch.
        interval:
            Candle interval — ``"1d"``, ``"1wk"``, ``"1mo"``.
        """
        yf_ticker = f"{ticker}.NS"
        end_date = date.today()
        start_date = end_date - timedelta(days=period_days)

        await self._rate_limiter.acquire()
        try:
            stock = yf.Ticker(yf_ticker)
            df: pd.DataFrame = stock.history(
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                interval=interval,
                auto_adjust=True,
            )
        except Exception:
            logger.exception("yfinance: OHLCV fetch failed for %s", ticker)
            return []

        if df.empty:
            logger.warning("yfinance: no OHLCV data returned for %s", ticker)
            return []

        records: list[dict[str, Any]] = []
        for timestamp, row in df.iterrows():
            records.append({
                "ticker": ticker,
                "timestamp": pd.Timestamp(timestamp).to_pydatetime().isoformat(),
                "open": _to_decimal(row.get("Open")),
                "high": _to_decimal(row.get("High")),
                "low": _to_decimal(row.get("Low")),
                "close": _to_decimal(row.get("Close")),
                "volume": int(row.get("Volume", 0)),
                "source": "yfinance",
            })
        return records

    # ------------------------------------------------------------------
    # Live / delayed price quotes
    # ------------------------------------------------------------------

    async def fetch_quote(self, ticker: str) -> dict[str, Any] | None:
        """Fetch the latest price quote for *ticker*.

        Returns a dict with current price, change, volume, and
        market-open status.
        """
        yf_ticker = f"{ticker}.NS"
        await self._rate_limiter.acquire()
        try:
            stock = yf.Ticker(yf_ticker)
            info = stock.info or {}
        except Exception:
            logger.exception("yfinance: quote fetch failed for %s", ticker)
            return None

        if not info:
            return None

        return {
            "ticker": ticker,
            "price": _to_decimal(info.get("currentPrice") or info.get("regularMarketPrice")),
            "previous_close": _to_decimal(info.get("previousClose") or info.get("regularMarketPreviousClose")),
            "change_pct": _to_decimal(info.get("regularMarketChangePercent")),
            "volume": info.get("volume") or info.get("regularMarketVolume"),
            "market_state": info.get("marketState", "UNKNOWN"),
            "timestamp": datetime.now().isoformat(),
            "source": "yfinance",
        }

    # ------------------------------------------------------------------
    # Basic fundamentals (for cross-validation)
    # ------------------------------------------------------------------

    async def fetch_fundamentals(self, ticker: str) -> dict[str, Any]:
        """Fetch basic fundamental data from yfinance for cross-validation."""
        yf_ticker = f"{ticker}.NS"
        await self._rate_limiter.acquire()
        try:
            stock = yf.Ticker(yf_ticker)
            info = stock.info or {}
        except Exception:
            logger.exception("yfinance: fundamentals fetch failed for %s", ticker)
            return {"ticker": ticker}

        return {
            "ticker": ticker,
            "market_cap": _to_decimal(info.get("marketCap")),
            "pe": _to_decimal(info.get("trailingPE")),
            "pb": _to_decimal(info.get("priceToBook")),
            "roe": _to_decimal(
                info.get("returnOnEquity") * 100 if info.get("returnOnEquity") else None
            ),
            "debt_equity": _to_decimal(info.get("debtToEquity")),
            "dividend_yield_pct": _to_decimal(
                info.get("dividendYield") * 100 if info.get("dividendYield") else None
            ),
            "eps": _to_decimal(info.get("trailingEps")),
            "revenue_growth_pct": _to_decimal(
                info.get("revenueGrowth") * 100 if info.get("revenueGrowth") else None
            ),
            "source": "yfinance",
        }

    # ------------------------------------------------------------------
    # Batch operations
    # ------------------------------------------------------------------

    async def fetch_ohlcv_batch(
        self,
        tickers: list[str],
        period_days: int = 365,
    ) -> list[dict[str, Any]]:
        """Fetch OHLCV for multiple tickers sequentially."""
        all_records: list[dict[str, Any]] = []
        for ticker in tickers:
            records = await self.fetch_ohlcv(ticker, period_days=period_days)
            all_records.extend(records)
        logger.info("yfinance: fetched %d OHLCV records for %d tickers", len(all_records), len(tickers))
        return all_records

    # ------------------------------------------------------------------
    # BaseScraper interface
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Default scrape — call ``fetch_ohlcv_batch`` or ``fetch_quote`` directly."""
        logger.info("yfinance: use fetch_ohlcv_batch() or fetch_quote() for targeted fetching")
        return []

    async def save(self, data: list[dict[str, Any]]) -> int:
        """Persist OHLCV data to the prices table."""
        from mr_market_shared.db.models import Price
        from mr_market_shared.db.session import get_session_manager

        manager = get_session_manager()
        saved = 0
        async with manager.session() as session:
            for record in data:
                price = Price(
                    ticker=record["ticker"],
                    timestamp=datetime.fromisoformat(record["timestamp"]),
                    open=record.get("open"),
                    high=record.get("high"),
                    low=record.get("low"),
                    close=record.get("close"),
                    volume=record.get("volume"),
                    source=record.get("source", "yfinance"),
                )
                session.add(price)
                saved += 1
            await session.commit()
        logger.info("yfinance: saved %d price records", saved)
        return saved


def _to_decimal(value: Any) -> Decimal | None:
    """Safely convert a value to Decimal."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None
