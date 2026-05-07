"""GET /technicals/{ticker} — recent indicator snapshot.

Reads from the `technicals` table (computed nightly by the worker). Returns
the latest bar's full indicator set + a small narrative ("RSI 67, neutral
zone; price above SMA-50 and SMA-200") plus the prior N bars in case the
caller wants to chart a series.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.technicals import Technicals
from app.db.session import get_session

router = APIRouter(tags=["technicals"])


def _serialise_row(row: Technicals) -> dict[str, Any]:
    out = {
        "ts": row.ts.astimezone(timezone.utc).isoformat() if row.ts else None,
        "close": _str(row.close),
        "rsi_14": _str(row.rsi_14),
        "macd": _str(row.macd),
        "macd_signal": _str(row.macd_signal),
        "macd_hist": _str(row.macd_hist),
        "bb_upper": _str(row.bb_upper),
        "bb_middle": _str(row.bb_middle),
        "bb_lower": _str(row.bb_lower),
        "sma_20": _str(row.sma_20),
        "sma_50": _str(row.sma_50),
        "sma_200": _str(row.sma_200),
        "ema_12": _str(row.ema_12),
        "ema_26": _str(row.ema_26),
        "atr_14": _str(row.atr_14),
        "vol_avg_20": row.vol_avg_20,
    }
    return out


def _str(d: Decimal | None) -> str | None:
    return str(d) if d is not None else None


def _build_summary(latest: Technicals | None) -> dict[str, Any]:
    """Light qualitative tags. No advice — pure observation language."""
    if latest is None or latest.close is None:
        return {"available": False}

    summary: dict[str, Any] = {"available": True}

    # RSI tag
    if latest.rsi_14 is not None:
        rsi_v = float(latest.rsi_14)
        summary["rsi_zone"] = (
            "overbought" if rsi_v >= 70
            else "oversold" if rsi_v <= 30
            else "neutral"
        )

    # Trend vs SMA-50 / SMA-200
    close_f = float(latest.close)
    if latest.sma_50 is not None:
        summary["above_sma50"] = close_f > float(latest.sma_50)
    if latest.sma_200 is not None:
        summary["above_sma200"] = close_f > float(latest.sma_200)

    # MACD direction
    if latest.macd is not None and latest.macd_signal is not None:
        m = float(latest.macd)
        s = float(latest.macd_signal)
        summary["macd_above_signal"] = m > s

    # BB squeeze / position
    if (
        latest.bb_upper is not None
        and latest.bb_lower is not None
        and latest.bb_middle is not None
    ):
        upper = float(latest.bb_upper)
        lower = float(latest.bb_lower)
        middle = float(latest.bb_middle)
        if middle > 0:
            summary["bb_width_pct"] = round((upper - lower) / middle * 100, 4)
        if close_f >= upper:
            summary["bb_position"] = "above_upper"
        elif close_f <= lower:
            summary["bb_position"] = "below_lower"
        elif close_f >= middle:
            summary["bb_position"] = "above_middle"
        else:
            summary["bb_position"] = "below_middle"

    return summary


@router.get("/technicals/{ticker}")
async def technicals(
    ticker: str,
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not ticker or len(ticker) > 32:
        raise HTTPException(status_code=400, detail="invalid ticker")
    sym = ticker.upper().strip()

    rows = (
        await session.execute(
            select(Technicals)
            .where(Technicals.ticker == sym)
            .order_by(desc(Technicals.ts))
            .limit(days)
        )
    ).scalars().all()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"no technicals for {sym} — has the compute worker run?",
        )

    latest = rows[0]
    series = [_serialise_row(r) for r in rows]   # newest-first

    return {
        "ticker": sym,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "latest_bar_ts": latest.ts.astimezone(timezone.utc).isoformat() if latest.ts else None,
        "summary": _build_summary(latest),
        "latest": _serialise_row(latest),
        "series": series,
    }
