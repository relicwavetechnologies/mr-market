"""Redis cache for triangulated quotes.

Two layers:
  1. Hot:    `quote:{ticker}` with short TTL (15 s during RTH, 1 h after hours).
  2. LKG:    `quote:lkg:{ticker}` (last known good — no TTL) so that if every
             upstream source is dead we can still serve the most recent
             confidence-HIGH/MED price with a "(stale, last verified at HH:MM)"
             warning.

Stored as JSON. Keys are lowercased.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import cast

from redis import asyncio as aioredis

from app.data.market_hours import is_rth
from app.data.types import Confidence, Quote, TriangulatedQuote

logger = logging.getLogger(__name__)

_HOT_TTL_RTH_S = 15
_HOT_TTL_OFFHOURS_S = 60 * 60  # 1 h


def _hot_key(ticker: str) -> str:
    return f"quote:{ticker.lower()}"


def _lkg_key(ticker: str) -> str:
    return f"quote:lkg:{ticker.lower()}"


def _quote_to_json(q: TriangulatedQuote) -> str:
    return json.dumps(q.to_dict())


def _quote_from_json(raw: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads(raw))


async def get_hot(redis: aioredis.Redis, ticker: str) -> dict[str, object] | None:
    raw = await redis.get(_hot_key(ticker))
    if raw is None:
        return None
    try:
        return _quote_from_json(raw)
    except json.JSONDecodeError:
        return None


async def get_lkg(redis: aioredis.Redis, ticker: str) -> dict[str, object] | None:
    raw = await redis.get(_lkg_key(ticker))
    if raw is None:
        return None
    try:
        return _quote_from_json(raw)
    except json.JSONDecodeError:
        return None


async def write(redis: aioredis.Redis, q: TriangulatedQuote) -> None:
    payload = _quote_to_json(q)
    ttl = _HOT_TTL_RTH_S if is_rth() else _HOT_TTL_OFFHOURS_S
    try:
        await redis.set(_hot_key(q.ticker), payload, ex=ttl)
        # Only persist HIGH/MED into LKG; LOW means we didn't pick a number.
        if q.confidence in (Confidence.HIGH, Confidence.MED) and q.price is not None:
            await redis.set(_lkg_key(q.ticker), payload)
    except Exception as e:  # noqa: BLE001
        logger.warning("redis cache write failed for %s: %s", q.ticker, e)


def stale_marker(payload: dict[str, object]) -> dict[str, object]:
    """Return a copy of an LKG payload tagged as stale, with age in seconds."""
    out = dict(payload)
    as_of = payload.get("as_of")
    age_s: float | None = None
    if isinstance(as_of, str):
        try:
            t = datetime.fromisoformat(as_of)
            age_s = (datetime.now(timezone.utc) - t).total_seconds()
        except Exception:
            age_s = None
    out["stale"] = True
    out["stale_age_s"] = age_s
    out["note"] = (
        f"All upstream sources unavailable. Showing last verified value "
        f"({age_s:.0f}s old)." if age_s is not None
        else "All upstream sources unavailable. Showing last verified value."
    )
    return out


def quote_dict_unchanged(payload: dict[str, object]) -> dict[str, object]:
    """Return the payload unchanged but typed for the caller."""
    return dict(payload)


def _ignored_quote_arg(_: Quote) -> None:  # pragma: no cover
    # Quote import is referenced for completeness — tooling sometimes
    # complains otherwise. Not actually called.
    return None
