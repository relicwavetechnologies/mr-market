"""Portfolio review endpoint — Phase 3 placeholder."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, DBSessionDep

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PortfolioHolding(BaseModel):
    """A single holding submitted for review."""
    ticker: str
    quantity: int
    avg_price: float


class PortfolioReviewRequest(BaseModel):
    """Client-submitted portfolio for analysis."""
    holdings: list[PortfolioHolding] = Field(..., min_length=1)


class PortfolioReviewResponse(BaseModel):
    """Analysis result for a portfolio."""
    summary: str
    risk_score: float | None = None
    sector_concentration: dict[str, float] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)
    disclaimer: str = (
        "SEBI Disclaimer: This is AI-generated analysis for educational purposes only. "
        "Not investment advice. Please consult a SEBI-registered advisor."
    )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/review", response_model=PortfolioReviewResponse)
async def review_portfolio(
    request: PortfolioReviewRequest,
    user_id: CurrentUserDep,
    db: DBSessionDep,
) -> PortfolioReviewResponse:
    """Analyse a user-submitted portfolio and return recommendations.

    Phase 3 implementation will:
      - Fetch live prices for each holding
      - Compute sector/industry concentration
      - Run risk metrics (beta, max drawdown)
      - Generate rebalancing suggestions based on user risk profile
    """
    tickers = [h.ticker.upper() for h in request.holdings]
    total_value = sum(h.quantity * h.avg_price for h in request.holdings)

    sector_map: dict[str, float] = {}
    for holding in request.holdings:
        weight = (holding.quantity * holding.avg_price) / total_value if total_value else 0
        sector_map[holding.ticker.upper()] = round(weight * 100, 2)

    return PortfolioReviewResponse(
        summary=(
            f"Portfolio contains {len(tickers)} stocks with a total invested "
            f"value of INR {total_value:,.2f}. Detailed analysis coming in Phase 3."
        ),
        risk_score=None,
        sector_concentration=sector_map,
        recommendations=[
            "Full portfolio analysis will be available in Phase 3.",
            "Consider diversifying across sectors for lower risk.",
        ],
    )
