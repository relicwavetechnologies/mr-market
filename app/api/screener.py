"""STUB endpoints for the Phase-3 screener surface.

This file is the day-1 hand-off from Dev A → Dev B. It exposes the four
screener routes Dev B will call from the LLM tool layer (`run_screener`),
returning **deterministic hard-coded payloads** so the LLM tool wiring,
verifier extension, and `ScreenerCard` UI work end-to-end before Dev A's
real screener engine lands in P3-A2 / P3-A3.

When the real implementation lands, the only change in this file is the
body of each handler — the route paths, request schemas, and response
shapes (locked in `app/contracts/phase3.md`) stay identical.

Stub mode is the default; flip to real once A-2 lands by replacing the
`_*_STUB` payloads with calls into `app.analytics.screener`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.screener import (
    ScreenerError,
    result_to_dict,
    run_screener,
)
from app.db.session import get_session

router = APIRouter(prefix="/screener", tags=["screener"])


# ---------------------------------------------------------------------------
# Hard-coded payloads — deterministic so Dev B's tests can pin them
# ---------------------------------------------------------------------------


_RUN_STUB: dict[str, Any] = {
    "matched": 3,
    "universe_size": 100,
    "exec_ms": 142,
    "tickers": [
        {
            "symbol": "RELIANCE",
            "score": 0.82,
            "hits": {
                "rsi_14": "28.4",
                "pe_trailing": "18.7",
                "promoter_pct": "50.0000",
            },
        },
        {
            "symbol": "TCS",
            "score": 0.71,
            "hits": {
                "rsi_14": "29.1",
                "pe_trailing": "19.5",
                "promoter_pct": "71.7700",
            },
        },
        {
            "symbol": "INFY",
            "score": 0.64,
            "hits": {
                "rsi_14": "27.2",
                "pe_trailing": "17.9",
                "promoter_pct": "13.2000",
            },
        },
    ],
}


_LIST_STUB: dict[str, Any] = {
    "screeners": [
        {
            "name": "oversold_quality",
            "expr": "rsi_14 < 30 AND pe_trailing < 25 AND promoter_pct > 50",
            "description": "Mean-reversion candidates with healthy fundamentals.",
            "is_seed": True,
            "created_by": None,
        },
        {
            "name": "value_rebound",
            "expr": "pe_trailing < 20 AND price < sma_200",
            "description": "Below-200DMA names trading at reasonable multiples.",
            "is_seed": True,
            "created_by": None,
        },
        {
            "name": "momentum_breakout",
            "expr": "rsi_14 > 65 AND price > sma_50 AND price > sma_200",
            "description": "Trending up across both moving averages, with momentum.",
            "is_seed": True,
            "created_by": None,
        },
        {
            "name": "high_pledge_avoid",
            "expr": "pledged_pct > 25",
            "description": "Promoter pledge over 25% — flag for caution.",
            "is_seed": True,
            "created_by": None,
        },
        {
            "name": "fii_buying",
            "expr": "fii_pct_qoq_delta > 0.5",
            "description": "FII share rose by ≥0.5pp last quarter.",
            "is_seed": True,
            "created_by": None,
        },
        {
            "name": "promoter_increasing",
            "expr": "promoter_pct_qoq_delta > 0.5",
            "description": "Promoter share rose by ≥0.5pp last quarter.",
            "is_seed": True,
            "created_by": None,
        },
    ],
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ScreenerRunRequest(BaseModel):
    expr: str | None = Field(
        default=None, description="Expression like 'rsi_14 < 30 AND pe_trailing < 20'"
    )
    name: str | None = Field(default=None, description="Name of a saved screener")
    limit: int = Field(default=50, ge=1, le=100)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/run")
async def post_run_screener(
    req: ScreenerRunRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not req.expr and not req.name:
        raise HTTPException(
            status_code=400, detail="either `expr` or `name` is required"
        )
    if req.expr and req.name:
        raise HTTPException(
            status_code=400, detail="pass `expr` OR `name`, not both"
        )

    # `expr` path is fully wired in A-2. `name` path stays stubbed until
    # A-3 ships the stored-screeners table; the contract shape stays
    # identical between the two phases.
    if req.expr:
        try:
            result = await run_screener(session, req.expr, limit=req.limit)
        except ScreenerError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return result_to_dict(result)

    # name path → stub (A-3 will replace this).
    out = dict(_RUN_STUB)
    out["tickers"] = out["tickers"][: req.limit]
    out["matched"] = len(out["tickers"])
    out["_stub"] = True
    return out


@router.get("/list")
async def list_screeners() -> dict[str, Any]:
    return {**_LIST_STUB, "_stub": True}


@router.get("/{name}")
async def get_screener(name: str) -> dict[str, Any]:
    for s in _LIST_STUB["screeners"]:
        if s["name"] == name:
            return {**s, "_stub": True}
    raise HTTPException(status_code=404, detail=f"screener {name!r} not found")
