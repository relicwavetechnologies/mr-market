"""High-level quote orchestrator: cache → triangulate → cache → return.

Flow:
  1. Hot cache hit  → return as-is.
  2. Otherwise fan-out to all sources via `triangulate.fetch_all`.
  3. If result is HIGH/MED → cache (hot + LKG) and return.
  4. If result is LOW (sources disagreed or 0–1 returned)
       → fall back to LKG with a `stale` marker.
       → if no LKG either, return the LOW result so the caller can
         surface "couldn't confidently fetch a price".
"""

from __future__ import annotations

import logging
import time
from typing import Any

from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.data import cache, triangulate
from app.data.sources import moneycontrol as mc_src
from app.data.sources import nse as nse_src
from app.data.sources import screener as scr_src
from app.data.sources import yf as yf_src
from app.data.types import Confidence, TriangulatedQuote
from app.db.models.scrape_log import ScrapeLog

logger = logging.getLogger(__name__)


SOURCES = {
    "yfinance": yf_src.fetch,
    "nselib": nse_src.fetch,
    "screener": scr_src.fetch,
    "moneycontrol": mc_src.fetch,
}


async def get_quote(
    ticker: str,
    redis: aioredis.Redis,
    session: AsyncSession | None = None,
    *,
    skip_cache: bool = False,
) -> dict[str, Any]:
    sym = ticker.upper().strip()

    if not skip_cache:
        hot = await cache.get_hot(redis, sym)
        if hot is not None:
            return {**hot, "cache": "hit"}

    started = time.perf_counter()
    tri = await triangulate.fetch_all(sym, SOURCES)
    duration_ms = int((time.perf_counter() - started) * 1000)

    if session is not None:
        await _log_scrape(session, sym, tri, duration_ms)

    if tri.confidence == Confidence.LOW:
        lkg = await cache.get_lkg(redis, sym)
        if lkg is not None:
            return {**cache.stale_marker(lkg), "cache": "lkg"}
        # No LKG, no confident price — return the LOW result honestly.
        return {**tri.to_dict(), "cache": "miss"}

    await cache.write(redis, tri)
    return {**tri.to_dict(), "cache": "miss"}


async def _log_scrape(
    session: AsyncSession,
    ticker: str,
    tri: TriangulatedQuote,
    duration_ms: int,
) -> None:
    try:
        # One row per attempt, summarised. Per-source success/fail goes in meta.
        row = ScrapeLog(
            source="quote",
            ok=tri.confidence != Confidence.LOW,
            status_code=None,
            duration_ms=duration_ms,
            error=tri.note,
            meta={
                "ticker": ticker,
                "confidence": tri.confidence.value,
                "spread_pct": str(tri.spread_pct),
                "ok_sources": [q.source for q in tri.sources],
                "failed_sources": tri.failed_sources,
            },
        )
        session.add(row)
        await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("scrape_log write failed for %s: %s", ticker, e)
        await session.rollback()
