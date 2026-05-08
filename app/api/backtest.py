"""Backtest endpoint (P3-A6).

`POST /backtest/run` is now wired to a real engine — replays a saved
screener over `prices_daily` for the requested window. Phase-3 ships
single-strategy backtests only (Decision #5). Multi-strategy is Phase-4.

Schemas locked in `app/contracts/phase3.md`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.backtest import (
    BacktestResult,
    result_to_dict,
    run_backtest,
)
from app.analytics.screener import ScreenerError
from app.db.models import Holding, PriceDaily, Stock
from app.db.models.screener import Screener
from app.db.session import get_session

router = APIRouter(prefix="/backtest", tags=["backtest"])


# Backtest results only need to refresh once per trading day (after the
# nightly EOD ingest) — 6 hours is generous and keeps the demo snappy.
_BACKTEST_CACHE_TTL_S = 6 * 3600


def _backtest_cache_key(name: str, period_days: int, holding_period: int) -> str:
    h = hashlib.sha256(
        f"{name}|p={period_days}|h={holding_period}".encode()
    ).hexdigest()[:16]
    return f"backtest:run:{h}"


class BacktestRunRequest(BaseModel):
    name: str = Field(..., description="saved screener name")
    period_days: int = Field(default=365, ge=30, le=730)
    holding_period: int = Field(default=5, ge=1, le=60)


@router.post("/run")
async def post_run_backtest(
    req: BacktestRunRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    # Resolve the screener.
    screener = (
        await session.execute(select(Screener).where(Screener.name == req.name))
    ).scalar_one_or_none()
    if screener is None:
        raise HTTPException(
            status_code=404, detail=f"screener {req.name!r} not found"
        )

    # P3-B6: Redis cache. Backtests are expensive (several hundred ms
    # per call); prices_daily only updates nightly, so a 6h TTL is safe.
    redis = getattr(request.app.state, "redis", None)
    cache_key = _backtest_cache_key(
        screener.name, req.period_days, req.holding_period
    )
    if redis is not None:
        try:
            cached = await redis.get(cache_key)
        except Exception:  # noqa: BLE001
            cached = None
        if cached:
            try:
                payload = json.loads(cached)
                payload["_cache"] = "hit"
                return payload
            except Exception:  # noqa: BLE001
                pass

    # Load price history — last (period_days + 200) for SMA-200 warmup.
    cutoff = dt.date.today() - dt.timedelta(days=req.period_days + 200)
    rows = (
        await session.execute(
            select(PriceDaily.ticker, PriceDaily.ts, PriceDaily.close)
            .where(PriceDaily.ts >= cutoff)
            .where(PriceDaily.source == "nsearchives")
            .order_by(PriceDaily.ticker, PriceDaily.ts)
        )
    ).all()
    price_history: dict[str, list[tuple[dt.date, float]]] = {}
    for ticker, ts, close in rows:
        if close is None:
            continue
        d = ts.date() if hasattr(ts, "date") else ts
        price_history.setdefault(ticker, []).append((d, float(close)))

    # Stock metadata maps.
    stocks = (await session.execute(select(Stock))).scalars().all()
    sector_map = {s.ticker: s.sector for s in stocks}

    # Latest holding row per ticker (frozen-in-time approximation).
    holdings = (
        await session.execute(
            select(Holding).order_by(desc(Holding.quarter_end))
        )
    ).scalars().all()
    promoter_map: dict[str, float] = {}
    public_map: dict[str, float] = {}
    for h in holdings:
        if h.ticker in promoter_map:
            continue
        if h.promoter_pct is not None:
            promoter_map[h.ticker] = float(h.promoter_pct)
        if h.public_pct is not None:
            public_map[h.ticker] = float(h.public_pct)

    try:
        result: BacktestResult = run_backtest(
            name=screener.name,
            expr=screener.expr,
            period_days=req.period_days,
            holding_period=req.holding_period,
            price_history=price_history,
            sector_map=sector_map,
            promoter_map=promoter_map,
            public_map=public_map,
        )
    except ScreenerError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    payload = result_to_dict(result)
    if redis is not None:
        try:
            await redis.set(
                cache_key, json.dumps(payload, default=str), ex=_BACKTEST_CACHE_TTL_S
            )
        except Exception:  # noqa: BLE001
            pass
    payload["_cache"] = "miss"
    return payload
