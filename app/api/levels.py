"""GET /levels/{ticker} — pivots + multi-touch S/R + Fibonacci retracements.

Computed on-demand from `prices_daily` (no separate cache table — the math is
fast and would need invalidation on every nightly ingest anyway).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.levels import compute_levels
from app.db.models.price import PriceDaily
from app.db.session import get_session

router = APIRouter(tags=["levels"])


@router.get("/levels/{ticker}")
async def levels(
    ticker: str,
    window: int = Query(90, ge=10, le=365),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not ticker or len(ticker) > 32:
        raise HTTPException(status_code=400, detail="invalid ticker")
    sym = ticker.upper().strip()

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
            .where(PriceDaily.ticker == sym)
            .where(PriceDaily.source == "nsearchives")
            .order_by(desc(PriceDaily.ts))
            .limit(window)
        )
    ).all()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"no prices for {sym} — has the EOD ingest run?",
        )

    df = pd.DataFrame(
        rows, columns=["ts", "open", "high", "low", "close", "volume"]
    ).sort_values("ts").set_index("ts")

    out = compute_levels(df, window=window)
    out["ticker"] = sym
    out["computed_at"] = datetime.now(timezone.utc).isoformat()
    return out
