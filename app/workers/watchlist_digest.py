"""Per-user watchlist daily digest (P3-A7).

Runs at 04:30 IST (23:00 UTC the previous day) — after the EOD
bhavcopy ingest at 22:30 UTC. Builds a per-user payload of overnight
moves on the user's watchlist tickers.

The digest is materialised as a Redis key per user (`digest:user:{id}`)
so the frontend can fetch it without a second LLM round trip when the
user logs in. Wire-up to email / push notifications is Phase-4.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PriceDaily, Watchlist
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DigestEntry:
    ticker: str
    close: Decimal
    prev_close: Decimal | None
    change_pct: float | None


@dataclass(slots=True)
class UserDigest:
    user_id: str
    tickers: list[DigestEntry]
    as_of: str
    n_movers: int


# ---------------------------------------------------------------------------
# Pure-functional builders (testable without DB / Redis)
# ---------------------------------------------------------------------------


def _change_pct(close: Decimal | float, prev: Decimal | float | None) -> float | None:
    if prev is None:
        return None
    try:
        prev_f = float(prev)
        close_f = float(close)
        if prev_f <= 0:
            return None
        return round((close_f - prev_f) / prev_f * 100, 2)
    except (TypeError, ValueError):
        return None


def build_digest(
    user_id: str,
    tickers: list[str],
    latest_closes: dict[str, tuple[date, Decimal]],
    prev_closes: dict[str, Decimal],
    *,
    mover_threshold_pct: float = 1.0,
) -> UserDigest:
    """Pure function: build a digest from pre-loaded close maps."""
    entries: list[DigestEntry] = []
    n_movers = 0
    as_of_date: date | None = None
    for t in tickers:
        latest = latest_closes.get(t)
        if not latest:
            continue
        d, close = latest
        if as_of_date is None or d > as_of_date:
            as_of_date = d
        prev = prev_closes.get(t)
        chg = _change_pct(close, prev)
        if chg is not None and abs(chg) >= mover_threshold_pct:
            n_movers += 1
        entries.append(
            DigestEntry(ticker=t, close=close, prev_close=prev, change_pct=chg)
        )
    return UserDigest(
        user_id=user_id,
        tickers=entries,
        as_of=as_of_date.isoformat() if as_of_date else "",
        n_movers=n_movers,
    )


def digest_to_json(d: UserDigest) -> dict[str, Any]:
    return {
        "user_id": d.user_id,
        "as_of": d.as_of,
        "n_tickers": len(d.tickers),
        "n_movers": d.n_movers,
        "tickers": [
            {
                "ticker": e.ticker,
                "close": str(e.close),
                "prev_close": str(e.prev_close) if e.prev_close is not None else None,
                "change_pct": e.change_pct,
            }
            for e in d.tickers
        ],
    }


# ---------------------------------------------------------------------------
# DB-backed runner
# ---------------------------------------------------------------------------


async def build_digests_for_all_users(session: AsyncSession) -> list[UserDigest]:
    """Group all watchlist rows by user; build a digest per user."""
    rows = (
        await session.execute(
            select(Watchlist.user_id, Watchlist.ticker).order_by(Watchlist.user_id)
        )
    ).all()
    by_user: dict[str, list[str]] = defaultdict(list)
    for user_id, ticker in rows:
        by_user[str(user_id)].append(ticker)

    if not by_user:
        return []

    # Latest two trading-day closes for every distinct ticker.
    all_tickers = sorted({t for ts in by_user.values() for t in ts})
    if not all_tickers:
        return []

    # Latest close per ticker.
    latest_subq = (
        select(PriceDaily.ticker, func.max(PriceDaily.ts).label("max_ts"))
        .where(PriceDaily.ticker.in_(all_tickers))
        .where(PriceDaily.source == "nsearchives")
        .group_by(PriceDaily.ticker)
        .subquery()
    )
    latest_rows = (
        await session.execute(
            select(PriceDaily.ticker, PriceDaily.ts, PriceDaily.close).join(
                latest_subq,
                (PriceDaily.ticker == latest_subq.c.ticker)
                & (PriceDaily.ts == latest_subq.c.max_ts),
            )
        )
    ).all()
    latest_closes: dict[str, tuple[date, Decimal]] = {}
    for ticker, ts, close in latest_rows:
        if close is None:
            continue
        d = ts.date() if hasattr(ts, "date") else ts
        latest_closes[ticker] = (d, close)

    # Prev close: second-most-recent ts per ticker.
    prev_closes: dict[str, Decimal] = {}
    for ticker in all_tickers:
        rows = (
            await session.execute(
                select(PriceDaily.close)
                .where(PriceDaily.ticker == ticker)
                .where(PriceDaily.source == "nsearchives")
                .order_by(desc(PriceDaily.ts))
                .limit(2)
            )
        ).scalars().all()
        if len(rows) >= 2 and rows[1] is not None:
            prev_closes[ticker] = rows[1]

    digests: list[UserDigest] = []
    for user_id, tickers in by_user.items():
        digests.append(
            build_digest(user_id, tickers, latest_closes, prev_closes)
        )
    return digests


# ---------------------------------------------------------------------------
# arq cron entry point
# ---------------------------------------------------------------------------


async def task_watchlist_digest(ctx) -> dict[str, Any]:
    """Build digests for all users and cache them in Redis under
    `digest:user:{id}` (TTL 36 h — covers a missed day plus the
    weekend market closure)."""
    redis = ctx.get("redis")
    async with SessionLocal() as session:
        digests = await build_digests_for_all_users(session)

    if redis is not None:
        for d in digests:
            try:
                await redis.set(
                    f"digest:user:{d.user_id}",
                    json.dumps(digest_to_json(d), default=str),
                    ex=36 * 3600,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("digest cache failed for %s: %s", d.user_id, e)

    return {
        "n_users": len(digests),
        "n_movers_total": sum(d.n_movers for d in digests),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
