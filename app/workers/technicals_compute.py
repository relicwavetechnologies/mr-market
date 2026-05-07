"""Technicals compute worker — `prices_daily` → `technicals` upsert.

Two entry points:
  - ``compute_for_ticker(session, ticker, *, lookback_days)`` —
    reads up to N most-recent bars, computes indicators, upserts ALL bars.
  - ``compute_for_universe(session)`` — fans out across every active ticker.
    Used by the nightly cron after EOD ingest finishes.

We always upsert every bar in the lookback window (not just the most recent)
because indicator values for bar N depend on bars N-200..N. If a backfill
adds older bars later, re-running is the correct way to recompute affected
rows. The composite PK + on_conflict_do_update keeps it idempotent and cheap.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.technicals import compute_indicators
from app.db.models.price import PriceDaily
from app.db.models.scrape_log import ScrapeLog
from app.db.models.stock import Stock
from app.db.models.technicals import Technicals

logger = logging.getLogger(__name__)


# Default lookback. SMA-200 needs ≥200 bars before its first valid value.
# A year of trading days is ~250 bars — gives us SMA-200 + ~50 valid days.
DEFAULT_LOOKBACK_DAYS = 365


@dataclass(slots=True)
class ComputeStats:
    ticker: str
    rows_in: int = 0
    rows_out: int = 0
    rows_with_rsi: int = 0
    rows_with_sma200: int = 0
    duration_ms: int = 0
    error: str | None = None

    def to_meta(self) -> dict:
        return {
            "ticker": self.ticker,
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "rows_with_rsi": self.rows_with_rsi,
            "rows_with_sma200": self.rows_with_sma200,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


async def _load_prices(session: AsyncSession, ticker: str, *, lookback_days: int) -> pd.DataFrame:
    rows = (
        await session.execute(
            select(
                PriceDaily.ts,
                PriceDaily.open,
                PriceDaily.high,
                PriceDaily.low,
                PriceDaily.close,
                PriceDaily.volume,
            )
            .where(PriceDaily.ticker == ticker)
            .where(PriceDaily.source == "nsearchives")
            .order_by(PriceDaily.ts.desc())
            .limit(lookback_days)
        )
    ).all()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        rows, columns=["ts", "open", "high", "low", "close", "volume"]
    )
    # We pulled DESC for the LIMIT to be cheap; flip to ASC for indicator math.
    df = df.sort_values("ts").reset_index(drop=True)
    df = df.set_index("ts")
    return df


def _to_decimal_safe(v):
    """Convert a pandas float to Decimal-friendly Python value or None."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if pd.isna(v):
        return None
    return v


async def _upsert(session: AsyncSession, ticker: str, indicators: pd.DataFrame) -> int:
    payload: list[dict] = []
    for ts, row in indicators.iterrows():
        payload.append(
            {
                "ticker": ticker,
                "ts": ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                "close": _to_decimal_safe(row["close"]),
                "rsi_14": _to_decimal_safe(row["rsi_14"]),
                "macd": _to_decimal_safe(row["macd"]),
                "macd_signal": _to_decimal_safe(row["macd_signal"]),
                "macd_hist": _to_decimal_safe(row["macd_hist"]),
                "bb_upper": _to_decimal_safe(row["bb_upper"]),
                "bb_middle": _to_decimal_safe(row["bb_middle"]),
                "bb_lower": _to_decimal_safe(row["bb_lower"]),
                "sma_20": _to_decimal_safe(row["sma_20"]),
                "sma_50": _to_decimal_safe(row["sma_50"]),
                "sma_200": _to_decimal_safe(row["sma_200"]),
                "ema_12": _to_decimal_safe(row["ema_12"]),
                "ema_26": _to_decimal_safe(row["ema_26"]),
                "atr_14": _to_decimal_safe(row["atr_14"]),
                "vol_avg_20": (
                    int(row["vol_avg_20"])
                    if not pd.isna(row["vol_avg_20"])
                    else None
                ),
            }
        )
    if not payload:
        return 0

    stmt = pg_insert(Technicals).values(payload)
    update_cols = {c: stmt.excluded[c] for c in payload[0] if c not in ("ticker", "ts")}
    stmt = stmt.on_conflict_do_update(
        index_elements=[Technicals.ticker, Technicals.ts],
        set_=update_cols,
    )
    await session.execute(stmt)
    return len(payload)


async def compute_for_ticker(
    session: AsyncSession,
    ticker: str,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> ComputeStats:
    started = time.perf_counter()
    stats = ComputeStats(ticker=ticker)

    try:
        prices = await _load_prices(session, ticker, lookback_days=lookback_days)
    except Exception as e:  # noqa: BLE001
        stats.error = f"load_prices: {e!s}"
        stats.duration_ms = int((time.perf_counter() - started) * 1000)
        return stats

    stats.rows_in = len(prices)
    if prices.empty:
        stats.error = "no prices for ticker"
        stats.duration_ms = int((time.perf_counter() - started) * 1000)
        return stats

    try:
        indicators = compute_indicators(prices)
    except Exception as e:  # noqa: BLE001
        stats.error = f"compute: {e!s}"
        stats.duration_ms = int((time.perf_counter() - started) * 1000)
        return stats

    upserted = await _upsert(session, ticker, indicators)
    stats.rows_out = upserted
    stats.rows_with_rsi = int(indicators["rsi_14"].notna().sum())
    stats.rows_with_sma200 = int(indicators["sma_200"].notna().sum())
    stats.duration_ms = int((time.perf_counter() - started) * 1000)

    await session.commit()
    return stats


async def compute_for_universe(
    session: AsyncSession,
    *,
    tickers: Iterable[str] | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[ComputeStats]:
    if tickers is None:
        rows = (
            await session.execute(select(Stock.ticker).where(Stock.active.is_(True)))
        ).scalars().all()
        tickers = [t.upper() for t in rows]

    out: list[ComputeStats] = []
    for t in tickers:
        s = await compute_for_ticker(session, t, lookback_days=lookback_days)
        out.append(s)
        logger.info(
            "technicals %s rows_in=%d out=%d rsi_n=%d sma200_n=%d ms=%d %s",
            t, s.rows_in, s.rows_out, s.rows_with_rsi, s.rows_with_sma200,
            s.duration_ms, s.error or "",
        )

    # Audit summary row
    try:
        ok = sum(1 for s in out if s.error is None)
        session.add(
            ScrapeLog(
                source="technicals_compute",
                ok=ok > 0,
                duration_ms=sum(s.duration_ms for s in out),
                error=None if ok == len(out) else f"{len(out) - ok} failures",
                meta={
                    "n_tickers": len(out),
                    "n_ok": ok,
                    "lookback_days": lookback_days,
                },
            )
        )
        await session.commit()
    except Exception:  # noqa: BLE001
        await session.rollback()

    return out
