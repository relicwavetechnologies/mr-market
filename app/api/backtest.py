"""STUB endpoint for the Phase-3 backtest surface.

Day-1 hand-off from Dev A → Dev B. Real implementation lands in P3-A6
(single-strategy × 12 months on `prices_daily`). Phase-3 Decision #5:
backtest is single-strategy, NOT multi-strategy — see Plan.

Schemas locked in `app/contracts/phase3.md`.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/backtest", tags=["backtest"])


def _stub_equity_curve(period_days: int) -> list[dict[str, str]]:
    """Deterministic curve so Dev B's BacktestCard can chart something
    real-looking against the stub. Real backtest replays prices_daily."""
    end = date(2026, 5, 8)
    start = end - timedelta(days=period_days)
    # Simple synthetic up-and-to-the-right with one drawdown segment.
    curve = []
    value = 1.0
    for i in range(period_days + 1):
        d = start + timedelta(days=i)
        # +0.0003 daily drift, -0.0015 during a 30-day drawdown band
        if 100 <= i < 130:
            value *= 0.9985
        else:
            value *= 1.0003
        curve.append({"date": d.isoformat(), "value": f"{value:.4f}"})
    return curve


class BacktestRunRequest(BaseModel):
    name: str = Field(..., description="saved screener name")
    period_days: int = Field(default=365, ge=30, le=730)


@router.post("/run")
async def run_backtest(req: BacktestRunRequest) -> dict[str, Any]:
    if req.name not in {
        "oversold_quality",
        "value_rebound",
        "momentum_breakout",
        "high_pledge_avoid",
        "fii_buying",
        "promoter_increasing",
    }:
        raise HTTPException(
            status_code=404, detail=f"screener {req.name!r} not found"
        )
    return {
        "name": req.name,
        "period_days": req.period_days,
        "n_signals": 47,
        "hit_rate": "0.58",
        "mean_return": "0.063",
        "worst_drawdown": "-0.094",
        "sharpe_proxy": "1.42",
        "equity_curve": _stub_equity_curve(req.period_days),
        "_stub": True,
    }
