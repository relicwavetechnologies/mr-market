"""End-of-day price ingester — bhavcopy → `prices_daily`.

Two entry points:
  - ``ingest_one_day(session, d, *, universe)`` — pulls one trading date and
    upserts every matching row. Idempotent: re-running with the same date
    overwrites existing rows for `(ticker, ts, source='nsearchives')`.
  - ``backfill(session, days)`` — walks back ``days`` calendar days from
    today, calls ``ingest_one_day`` for each weekday. Soft-skips weekends /
    holidays (BhavcopyMissing).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources.nse_archive import (
    BhavcopyError,
    BhavcopyMissing,
    BhavRow,
    fetch_rows,
    likely_trading_day,
    utc_close_of_day,
)
from app.db.models.price import PriceDaily
from app.db.models.scrape_log import ScrapeLog
from app.db.models.stock import Stock

logger = logging.getLogger(__name__)

SOURCE = "nsearchives"


@dataclass(slots=True)
class IngestStats:
    trade_date: str
    fetched: int = 0          # rows pulled from CSV
    upserted: int = 0         # rows written to DB (insert + update)
    skipped_no_universe: int = 0
    duration_ms: int = 0
    error: str | None = None

    def to_meta(self) -> dict:
        return {
            "trade_date": self.trade_date,
            "fetched": self.fetched,
            "upserted": self.upserted,
            "skipped_no_universe": self.skipped_no_universe,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


async def _active_universe(session: AsyncSession) -> set[str]:
    rows = (
        await session.execute(select(Stock.ticker).where(Stock.active.is_(True)))
    ).scalars().all()
    return {t.upper() for t in rows}


async def _upsert_rows(session: AsyncSession, rows: Iterable[BhavRow]) -> int:
    """Upsert into `prices_daily`, returning the affected-row count.

    Composite PK is (ticker, ts, source); on conflict we update OHLC + volume
    so reruns are idempotent and self-correcting if NSE later restates a bar.
    """
    payload = []
    for r in rows:
        payload.append(
            {
                "ticker": r.ticker,
                "ts": utc_close_of_day(r.trade_date),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "prev_close": r.prev_close,
                "volume": r.volume,
                "source": SOURCE,
            }
        )
    if not payload:
        return 0

    stmt = pg_insert(PriceDaily).values(payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=[PriceDaily.ticker, PriceDaily.ts, PriceDaily.source],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "prev_close": stmt.excluded.prev_close,
            "volume": stmt.excluded.volume,
        },
    )
    await session.execute(stmt)
    return len(payload)


async def ingest_one_day(
    session: AsyncSession,
    d: date,
    *,
    universe: Iterable[str] | None = None,
) -> IngestStats:
    """Fetch + upsert one trading date. Always returns a stats object;
    transient errors are recorded in `stats.error` rather than raised, so
    the cron driver can keep going.
    """
    started = time.perf_counter()
    stats = IngestStats(trade_date=d.isoformat())

    if not likely_trading_day(d):
        stats.error = "weekend"
        stats.duration_ms = int((time.perf_counter() - started) * 1000)
        return stats

    if universe is None:
        universe = await _active_universe(session)
    universe_set = {u.upper() for u in universe}

    try:
        rows = await fetch_rows(d, universe=universe_set)
    except BhavcopyMissing as e:
        stats.error = f"missing: {e}"
        stats.duration_ms = int((time.perf_counter() - started) * 1000)
        await _log(session, stats, ok=False)
        return stats
    except BhavcopyError as e:
        stats.error = f"fetch: {type(e).__name__}: {e}"
        stats.duration_ms = int((time.perf_counter() - started) * 1000)
        await _log(session, stats, ok=False)
        return stats

    stats.fetched = len(rows)

    upserted = await _upsert_rows(session, rows)
    stats.upserted = upserted
    stats.duration_ms = int((time.perf_counter() - started) * 1000)

    await _log(session, stats, ok=True)
    await session.commit()
    return stats


async def _log(session: AsyncSession, stats: IngestStats, *, ok: bool) -> None:
    try:
        session.add(
            ScrapeLog(
                source="eod_bhavcopy",
                ok=ok,
                duration_ms=stats.duration_ms,
                error=stats.error,
                meta=stats.to_meta(),
            )
        )
        await session.commit()
    except Exception:  # noqa: BLE001
        await session.rollback()


async def backfill(
    session: AsyncSession,
    *,
    days: int,
    end: date | None = None,
) -> list[IngestStats]:
    """Walk back ``days`` calendar days from ``end`` (default = today, IST).

    Holidays / weekends are soft-skipped. Order of work is oldest-first so the
    DB grows chronologically — easier for downstream technicals to compute.
    """
    if days <= 0:
        return []
    if end is None:
        # Calendar 'today' in IST is sufficient for the cutoff; the bhavcopy
        # for "today" is published ~6 PM IST so a same-day call may 404.
        from app.data.market_hours import IST

        end = (
            __import__("datetime")
            .datetime.now(IST)
            .date()
        )

    universe = await _active_universe(session)
    out: list[IngestStats] = []

    # Iterate oldest first.
    for offset in range(days, -1, -1):
        d = end - timedelta(days=offset)
        if not likely_trading_day(d):
            continue
        stats = await ingest_one_day(session, d, universe=universe)
        out.append(stats)
        logger.info(
            "eod_ingest %s fetched=%d upserted=%d err=%s",
            stats.trade_date, stats.fetched, stats.upserted, stats.error,
        )
    return out
