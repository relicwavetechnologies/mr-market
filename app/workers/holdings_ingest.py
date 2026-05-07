"""Holdings ingest worker — NSE shareholding API → `holdings` table.

Two entry points:
  - ``ingest_for_ticker(session, ticker)`` — full historical pull for one
    symbol; idempotent upsert on `(ticker, quarter_end)`.
  - ``ingest_for_universe(session)`` — fan-out across active stocks with a
    small inter-call delay so we don't hammer NSE.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources.nse_shareholding import (
    HoldingRow,
    ShareholdingError,
    ShareholdingMissing,
    fetch,
)
from app.db.models.holding import Holding
from app.db.models.scrape_log import ScrapeLog
from app.db.models.stock import Stock

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestStats:
    ticker: str
    fetched: int = 0
    upserted: int = 0
    duration_ms: int = 0
    error: str | None = None

    def to_meta(self) -> dict:
        return {
            "ticker": self.ticker,
            "fetched": self.fetched,
            "upserted": self.upserted,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


def _dedupe_keep_latest(rows: Iterable[HoldingRow]) -> list[HoldingRow]:
    """NSE returns multiple records per `(ticker, quarter_end)` when a filing
    is revised. Postgres can't `ON CONFLICT DO UPDATE` against duplicate keys
    in the same INSERT, so we collapse here. We keep the row with the latest
    broadcast_date (or submission_date as a fallback)."""
    by_key: dict[tuple[str, object], HoldingRow] = {}
    for r in rows:
        key = (r.ticker, r.quarter_end)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = r
            continue
        # Tiebreak: latest broadcast_date wins; then latest submission_date.
        ec = existing.broadcast_date or existing.submission_date
        rc = r.broadcast_date or r.submission_date
        if rc is not None and (ec is None or rc > ec):
            by_key[key] = r
    return list(by_key.values())


async def _upsert(session: AsyncSession, rows: Iterable[HoldingRow]) -> int:
    deduped = _dedupe_keep_latest(rows)
    payload = [
        {
            "ticker": r.ticker,
            "quarter_end": r.quarter_end,
            "promoter_pct": r.promoter_pct,
            "public_pct": r.public_pct,
            "employee_trust_pct": r.employee_trust_pct,
            "xbrl_url": r.xbrl_url,
            "submission_date": r.submission_date,
            "broadcast_date": r.broadcast_date,
            "raw": r.raw,
        }
        for r in deduped
    ]
    if not payload:
        return 0
    stmt = pg_insert(Holding).values(payload)
    update_cols = {
        c: stmt.excluded[c]
        for c in payload[0]
        if c not in ("ticker", "quarter_end")
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=[Holding.ticker, Holding.quarter_end],
        set_=update_cols,
    )
    await session.execute(stmt)
    return len(payload)


async def ingest_for_ticker(session: AsyncSession, ticker: str) -> IngestStats:
    started = time.perf_counter()
    sym = ticker.upper().strip()
    stats = IngestStats(ticker=sym)
    try:
        rows = await fetch(sym)
    except ShareholdingMissing as e:
        stats.error = f"missing: {e}"
        stats.duration_ms = int((time.perf_counter() - started) * 1000)
        await _audit(session, stats, ok=False)
        return stats
    except ShareholdingError as e:
        stats.error = f"fetch: {type(e).__name__}: {e}"
        stats.duration_ms = int((time.perf_counter() - started) * 1000)
        await _audit(session, stats, ok=False)
        return stats

    stats.fetched = len(rows)
    upserted = await _upsert(session, rows)
    stats.upserted = upserted
    stats.duration_ms = int((time.perf_counter() - started) * 1000)
    await session.commit()
    await _audit(session, stats, ok=True)
    return stats


async def _audit(session: AsyncSession, stats: IngestStats, *, ok: bool) -> None:
    try:
        session.add(
            ScrapeLog(
                source="holdings",
                ok=ok,
                duration_ms=stats.duration_ms,
                error=stats.error,
                meta=stats.to_meta(),
            )
        )
        await session.commit()
    except Exception:  # noqa: BLE001
        await session.rollback()


async def ingest_for_universe(
    session: AsyncSession,
    *,
    tickers: Iterable[str] | None = None,
    delay_s: float = 0.5,
) -> list[IngestStats]:
    if tickers is None:
        rows = (
            await session.execute(select(Stock.ticker).where(Stock.active.is_(True)))
        ).scalars().all()
        tickers = [t.upper() for t in rows]

    out: list[IngestStats] = []
    for t in tickers:
        s = await ingest_for_ticker(session, t)
        out.append(s)
        logger.info(
            "holdings %s fetched=%d upserted=%d ms=%d %s",
            t, s.fetched, s.upserted, s.duration_ms, s.error or "",
        )
        if delay_s > 0:
            await asyncio.sleep(delay_s)
    return out
