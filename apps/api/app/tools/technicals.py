"""TechnicalsTool — retrieve or compute technical indicators for a ticker."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.base import BaseTool
from mr_market_shared.db.models import Technical, Price

logger = logging.getLogger(__name__)


class TechnicalsTool(BaseTool):
    """Return technical indicators for a given ticker.

    Reads pre-computed values from the ``technicals`` table.  If no recent
    row exists, computes on-the-fly using pandas-ta over the last 200 days
    of OHLCV data.
    """

    name = "calc_technicals"
    description = (
        "Get technical indicators (RSI, MACD, Bollinger Bands, SMA, EMA, "
        "pivot points, ATR, trend) for an Indian stock."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "NSE ticker symbol",
            },
        },
        "required": ["ticker"],
    }

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        ticker: str = kwargs["ticker"].upper().strip()

        # Try pre-computed data first
        stored = await self._fetch_stored(ticker)
        if stored:
            return stored

        # Compute on the fly from raw OHLCV
        computed = await self._compute_live(ticker)
        if computed:
            return computed

        return {"error": f"No technical data available for {ticker}", "ticker": ticker}

    async def _fetch_stored(self, ticker: str) -> dict[str, Any] | None:
        """Load the latest pre-computed technical row."""
        stmt = (
            select(Technical)
            .where(Technical.ticker == ticker)
            .order_by(Technical.computed_date.desc())
            .limit(1)
        )
        row = (await self._db.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None

        return {
            "ticker": row.ticker,
            "computed_date": row.computed_date.isoformat(),
            "rsi_14": float(row.rsi_14) if row.rsi_14 else None,
            "macd": float(row.macd) if row.macd else None,
            "macd_signal": float(row.macd_signal) if row.macd_signal else None,
            "bb_upper": float(row.bb_upper) if row.bb_upper else None,
            "bb_lower": float(row.bb_lower) if row.bb_lower else None,
            "sma_20": float(row.sma_20) if row.sma_20 else None,
            "sma_50": float(row.sma_50) if row.sma_50 else None,
            "sma_200": float(row.sma_200) if row.sma_200 else None,
            "ema_20": float(row.ema_20) if row.ema_20 else None,
            "pivot": float(row.pivot) if row.pivot else None,
            "support_1": float(row.support_1) if row.support_1 else None,
            "support_2": float(row.support_2) if row.support_2 else None,
            "resistance_1": float(row.resistance_1) if row.resistance_1 else None,
            "resistance_2": float(row.resistance_2) if row.resistance_2 else None,
            "atr": float(row.atr) if row.atr else None,
            "trend": row.trend,
            "source": "database",
        }

    async def _compute_live(self, ticker: str) -> dict[str, Any] | None:
        """Compute technicals from raw OHLCV using pandas-ta."""
        stmt = (
            select(Price)
            .where(Price.ticker == ticker)
            .order_by(Price.timestamp.asc())
            .limit(200)
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        if len(rows) < 20:
            return None

        import pandas as pd

        df = pd.DataFrame([
            {
                "open": float(r.open) if r.open else 0,
                "high": float(r.high) if r.high else 0,
                "low": float(r.low) if r.low else 0,
                "close": float(r.close) if r.close else 0,
                "volume": r.volume or 0,
            }
            for r in rows
        ])

        from app.analytics.technicals import TechnicalAnalyzer

        analyzer = TechnicalAnalyzer()
        indicators = analyzer.compute_all(df)
        trend = analyzer.detect_trend(df)

        return {
            "ticker": ticker,
            "computed_date": datetime.now(timezone.utc).date().isoformat(),
            **indicators,
            "trend": trend,
            "source": "computed",
        }
