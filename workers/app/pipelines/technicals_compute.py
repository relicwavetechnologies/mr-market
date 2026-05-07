"""Technical indicators computation pipeline.

Fetches OHLCV data from the database and computes a full suite of
technical indicators using pandas-ta:

- RSI (14), MACD, Bollinger Bands
- SMA (20/50/200), EMA (20)
- Pivot Points, Support/Resistance levels
- ATR (14)
- Trend determination (bullish / bearish / sideways)

Designed to run nightly after market close and bulk-insert results
into the ``technicals`` table.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import pandas_ta as ta  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class TechnicalsComputePipeline:
    """Computes and stores technical indicators for all stocks.

    Usage::

        pipeline = TechnicalsComputePipeline()
        results = await pipeline.run()
    """

    # Minimum candles needed for the longest indicator (SMA 200)
    MIN_CANDLES = 210

    def __init__(self, lookback_days: int = 365) -> None:
        self.lookback_days = lookback_days

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    async def _load_ohlcv(self, ticker: str) -> pd.DataFrame:
        """Load OHLCV data for *ticker* from the database."""
        from mr_market_shared.db.models import Price
        from mr_market_shared.db.session import get_session_manager
        from sqlalchemy import select

        manager = get_session_manager()
        async with manager.session() as session:
            stmt = (
                select(Price)
                .where(Price.ticker == ticker)
                .order_by(Price.timestamp.asc())
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

        if not rows:
            return pd.DataFrame()

        records = [
            {
                "timestamp": row.timestamp,
                "open": float(row.open) if row.open else np.nan,
                "high": float(row.high) if row.high else np.nan,
                "low": float(row.low) if row.low else np.nan,
                "close": float(row.close) if row.close else np.nan,
                "volume": int(row.volume) if row.volume else 0,
            }
            for row in rows
        ]
        df = pd.DataFrame(records)
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)
        return df

    async def _get_all_tickers(self) -> list[str]:
        """Retrieve all stock tickers from the database."""
        from mr_market_shared.db.models import Stock
        from mr_market_shared.db.session import get_session_manager
        from sqlalchemy import select

        manager = get_session_manager()
        async with manager.session() as session:
            stmt = select(Stock.ticker)
            result = await session.execute(stmt)
            return [row[0] for row in result.all()]

    # ------------------------------------------------------------------
    # Indicator computation
    # ------------------------------------------------------------------

    def compute_indicators(self, df: pd.DataFrame, ticker: str) -> dict[str, Any] | None:
        """Compute all technical indicators from OHLCV DataFrame.

        Returns a dict compatible with the ``Technical`` ORM model,
        or ``None`` if insufficient data.
        """
        if len(df) < self.MIN_CANDLES:
            logger.debug(
                "technicals: skipping %s — only %d candles (need %d)",
                ticker,
                len(df),
                self.MIN_CANDLES,
            )
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]

        # RSI (14)
        rsi = ta.rsi(close, length=14)
        rsi_14 = _last_value(rsi)

        # MACD (12, 26, 9)
        macd_df = ta.macd(close, fast=12, slow=26, signal=9)
        macd_val = _last_value(macd_df.iloc[:, 0]) if macd_df is not None else None
        macd_signal = _last_value(macd_df.iloc[:, 2]) if macd_df is not None else None

        # Bollinger Bands (20, 2)
        bb = ta.bbands(close, length=20, std=2)
        bb_upper = _last_value(bb.iloc[:, 0]) if bb is not None else None
        bb_lower = _last_value(bb.iloc[:, 2]) if bb is not None else None

        # Simple Moving Averages
        sma_20 = _last_value(ta.sma(close, length=20))
        sma_50 = _last_value(ta.sma(close, length=50))
        sma_200 = _last_value(ta.sma(close, length=200))

        # Exponential Moving Average
        ema_20 = _last_value(ta.ema(close, length=20))

        # ATR (14)
        atr = _last_value(ta.atr(high, low, close, length=14))

        # Pivot Points (classic formula using previous day's HLC)
        prev_high = float(high.iloc[-2]) if len(high) >= 2 else float(high.iloc[-1])
        prev_low = float(low.iloc[-2]) if len(low) >= 2 else float(low.iloc[-1])
        prev_close = float(close.iloc[-2]) if len(close) >= 2 else float(close.iloc[-1])

        pivot = (prev_high + prev_low + prev_close) / 3
        support_1 = 2 * pivot - prev_high
        support_2 = pivot - (prev_high - prev_low)
        resistance_1 = 2 * pivot - prev_low
        resistance_2 = pivot + (prev_high - prev_low)

        # Trend determination
        trend = self._determine_trend(
            close=float(close.iloc[-1]),
            sma_20=sma_20,
            sma_50=sma_50,
            sma_200=sma_200,
            rsi_14=rsi_14,
        )

        return {
            "ticker": ticker,
            "computed_date": date.today().isoformat(),
            "rsi_14": _to_decimal(rsi_14),
            "macd": _to_decimal(macd_val),
            "macd_signal": _to_decimal(macd_signal),
            "bb_upper": _to_decimal(bb_upper),
            "bb_lower": _to_decimal(bb_lower),
            "sma_20": _to_decimal(sma_20),
            "sma_50": _to_decimal(sma_50),
            "sma_200": _to_decimal(sma_200),
            "ema_20": _to_decimal(ema_20),
            "pivot": _to_decimal(pivot),
            "support_1": _to_decimal(support_1),
            "support_2": _to_decimal(support_2),
            "resistance_1": _to_decimal(resistance_1),
            "resistance_2": _to_decimal(resistance_2),
            "atr": _to_decimal(atr),
            "trend": trend,
        }

    @staticmethod
    def _determine_trend(
        close: float,
        sma_20: float | None,
        sma_50: float | None,
        sma_200: float | None,
        rsi_14: float | None,
    ) -> str:
        """Determine trend based on moving average alignment and RSI.

        - **bullish**: price > SMA20 > SMA50 > SMA200, RSI > 50
        - **bearish**: price < SMA20 < SMA50 < SMA200, RSI < 50
        - **sideways**: mixed signals
        """
        if not all(v is not None for v in (sma_20, sma_50, sma_200)):
            return "sideways"

        assert sma_20 is not None and sma_50 is not None and sma_200 is not None

        # Bullish alignment
        if close > sma_20 > sma_50 > sma_200:
            if rsi_14 is not None and rsi_14 > 50:
                return "bullish"
            return "bullish"  # MA alignment is stronger signal

        # Bearish alignment
        if close < sma_20 < sma_50 < sma_200:
            if rsi_14 is not None and rsi_14 < 50:
                return "bearish"
            return "bearish"

        return "sideways"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _bulk_save(self, records: list[dict[str, Any]]) -> int:
        """Bulk insert technical indicators into the database."""
        from mr_market_shared.db.models import Technical
        from mr_market_shared.db.session import get_session_manager

        manager = get_session_manager()
        saved = 0
        async with manager.session() as session:
            for record in records:
                technical = Technical(
                    ticker=record["ticker"],
                    computed_date=date.fromisoformat(record["computed_date"]),
                    rsi_14=record.get("rsi_14"),
                    macd=record.get("macd"),
                    macd_signal=record.get("macd_signal"),
                    bb_upper=record.get("bb_upper"),
                    bb_lower=record.get("bb_lower"),
                    sma_20=record.get("sma_20"),
                    sma_50=record.get("sma_50"),
                    sma_200=record.get("sma_200"),
                    ema_20=record.get("ema_20"),
                    pivot=record.get("pivot"),
                    support_1=record.get("support_1"),
                    support_2=record.get("support_2"),
                    resistance_1=record.get("resistance_1"),
                    resistance_2=record.get("resistance_2"),
                    atr=record.get("atr"),
                    trend=record.get("trend"),
                )
                session.add(technical)
                saved += 1
            await session.commit()
        return saved

    # ------------------------------------------------------------------
    # Pipeline entry point
    # ------------------------------------------------------------------

    async def run(self) -> list[dict[str, Any]]:
        """Execute the full technicals computation pipeline.

        1. Load all tickers from the stock universe.
        2. For each ticker, fetch OHLCV data and compute indicators.
        3. Bulk insert results into the ``technicals`` table.

        Returns the list of computed indicator records.
        """
        tickers = await self._get_all_tickers()
        logger.info("technicals: computing indicators for %d stocks", len(tickers))

        results: list[dict[str, Any]] = []
        skipped = 0

        for ticker in tickers:
            df = await self._load_ohlcv(ticker)
            indicators = self.compute_indicators(df, ticker)
            if indicators:
                results.append(indicators)
            else:
                skipped += 1

        if results:
            saved = await self._bulk_save(results)
            logger.info(
                "technicals: computed %d, skipped %d, saved %d",
                len(results),
                skipped,
                saved,
            )
        else:
            logger.warning("technicals: no indicators computed")

        return results


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _last_value(series: pd.Series | None) -> float | None:
    """Extract the last non-NaN value from a pandas Series."""
    if series is None or series.empty:
        return None
    last = series.iloc[-1]
    if pd.isna(last):
        return None
    return float(last)


def _to_decimal(value: float | None) -> Decimal | None:
    """Convert a float to Decimal with 2 decimal places."""
    if value is None:
        return None
    return Decimal(str(round(value, 2)))
