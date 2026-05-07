"""STUB endpoints for the Phase-3 portfolio surface.

Day-1 hand-off from Dev A → Dev B. Real implementation lands in P3-A4
(import) / P3-A5 (diagnostics). Schemas and shapes are locked in
`app/contracts/phase3.md`; this file only wraps them with deterministic
payloads so Dev B can wire `analyse_portfolio` + `PortfolioCard` end-to-end.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


_DIAG_STUB: dict[str, Any] = {
    "portfolio_id": 17,
    "as_of": "2026-05-08",
    "n_positions": 12,
    "total_value_inr": "284200.00",
    "concentration": {
        "top_5_pct": "62.4",
        "herfindahl": "0.18",
    },
    "sector_pct": [
        {"sector": "Financial Services", "pct": "38.5"},
        {"sector": "IT", "pct": "22.1"},
        {"sector": "Energy", "pct": "15.0"},
        {"sector": "Consumer Goods", "pct": "12.4"},
        {"sector": "Pharma", "pct": "7.0"},
        {"sector": "Other", "pct": "5.0"},
    ],
    "beta_blend": "1.04",
    "div_yield": "1.85",
    "drawdown_1y": "-7.4",
}


class PortfolioHolding(BaseModel):
    ticker: str
    quantity: int = Field(ge=1)
    avg_price: str | None = None


class PortfolioImportRequest(BaseModel):
    format: str = Field(default="csv", description="csv | cdsl_paste")
    holdings: list[PortfolioHolding]


@router.post("/import")
async def import_portfolio(req: PortfolioImportRequest) -> dict[str, Any]:
    n = len(req.holdings)
    # Naive total: ignore avg_price; real impl uses live quote.
    return {
        "portfolio_id": 17,
        "n_positions": n,
        "total_cost_inr": "274350.00",
        "_stub": True,
    }


@router.get("/{portfolio_id}/diagnostics")
async def diagnostics(portfolio_id: int) -> dict[str, Any]:
    out = dict(_DIAG_STUB)
    out["portfolio_id"] = portfolio_id
    out["_stub"] = True
    return out
