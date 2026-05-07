"""Bulk + block deals ingest worker.

`nselib` returns one flat DataFrame for the whole market per call. We fetch
once, parse, filter to our active universe, dedupe, and bulk-upsert with
`ON CONFLICT DO NOTHING` against the natural-key unique constraint.

One ingest covers both kinds in two calls; rerunning is idempotent.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources.nse_deals import (
    DealKind,
    DealRow,
    DealsError,
    fetch as fetch_deals,
)
from app.db.models.deal import Deal
from app.db.models.scrape_log import ScrapeLog
from app.db.models.stock import Stock

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestStats:
    kind: DealKind
    period: str
    fetched: int = 0
    matched_universe: int = 0
    upserted: int = 0
    duration_ms: int = 0
    error: str | None = None

    def to_meta(self) -> dict:
        return {
            "kind": self.kind,
            "period": self.period,
            "fetched": self.fetched,
            "matched_universe": self.matched_universe,
            "upserted": self.upserted,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


async def _active_universe(session: AsyncSession) -> set[str]:
    rows = (
        await session.execute(select(Stock.ticker).where(Stock.active.is_(True)))
    ).scalars().all()
    return {t.upper() for t in rows}


def _dedupe_natural_key(rows: Iterable[DealRow]) -> list[DealRow]:
    """Collapse exact duplicates so the bulk INSERT doesn't trip the unique
    constraint twice in one statement."""
    seen: set[tuple] = set()
    out: list[DealRow] = []
    for r in rows:
        k = (
            r.trade_date, r.symbol, r.client_name, r.side, r.kind,
            r.quantity, r.avg_price,
        )
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


async def _upsert(session: AsyncSession, rows: list[DealRow]) -> int:
    if not rows:
        return 0
    payload = [
        {
            "trade_date": r.trade_date,
            "symbol": r.symbol,
            "security_name": r.security_name or None,
            "client_name": r.client_name,
            "side": r.side,
            "quantity": r.quantity,
            "avg_price": r.avg_price,
            "remarks": r.remarks,
            "kind": r.kind,
        }
        for r in rows
    ]
    stmt = pg_insert(Deal).values(payload).on_conflict_do_nothing(
        constraint="uq_deals_natural"
    )
    result = await session.execute(stmt)
    # rowcount on do_nothing = rows actually inserted.
    return int(result.rowcount or 0)


async def ingest_deals(
    session: AsyncSession,
    *,
    kind: DealKind,
    period: str = "1M",
) -> IngestStats:
    started = time.perf_counter()
    stats = IngestStats(kind=kind, period=period)

    try:
        rows = await fetch_deals(kind=kind, period=period)
    except DealsError as e:
        stats.error = f"{type(e).__name__}: {e}"
        stats.duration_ms = int((time.perf_counter() - started) * 1000)
        await _audit(session, stats, ok=False)
        return stats

    stats.fetched = len(rows)

    universe = await _active_universe(session)
    in_universe = [r for r in rows if r.symbol in universe]
    stats.matched_universe = len(in_universe)

    deduped = _dedupe_natural_key(in_universe)

    inserted = await _upsert(session, deduped)
    await session.commit()
    stats.upserted = inserted
    stats.duration_ms = int((time.perf_counter() - started) * 1000)
    await _audit(session, stats, ok=True)
    return stats


async def _audit(session: AsyncSession, stats: IngestStats, *, ok: bool) -> None:
    try:
        session.add(
            ScrapeLog(
                source=f"deals_{stats.kind}",
                ok=ok,
                duration_ms=stats.duration_ms,
                error=stats.error,
                meta=stats.to_meta(),
            )
        )
        await session.commit()
    except Exception:  # noqa: BLE001
        await session.rollback()


async def ingest_both(session: AsyncSession, *, period: str = "1M") -> list[IngestStats]:
    out: list[IngestStats] = []
    for kind in ("bulk", "block"):
        s = await ingest_deals(session, kind=kind, period=period)  # type: ignore[arg-type]
        out.append(s)
        logger.info(
            "deals %s period=%s fetched=%d matched=%d upserted=%d ms=%d %s",
            kind, period, s.fetched, s.matched_universe, s.upserted,
            s.duration_ms, s.error or "",
        )
    return out
