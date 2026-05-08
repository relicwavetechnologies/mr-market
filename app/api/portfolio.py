"""Portfolio REST endpoints (P3-A4 = import; P3-A5 = diagnostics).

Today (P3-A4):
- `POST /portfolio/import` — fully wired. Accepts either a pre-parsed
  `holdings` array OR a `raw_text` blob the server parses as CSV or
  Zerodha-CDSL paste. Persists to `portfolios` + `holdings_user` for the
  authenticated user. Auth required (PM-1 JWT).
- `GET /portfolio/{id}/diagnostics` — STILL stubbed; the real diagnostics
  pipeline lands in P3-A5.

Schemas locked in `app/contracts/phase3.md`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.data.portfolio_import import (
    ParsedHolding,
    collapse_duplicates,
    parse_text,
)
from app.db.models import HoldingUser, Portfolio, Stock, User
from app.db.session import get_session

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


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PortfolioHolding(BaseModel):
    ticker: str
    quantity: int = Field(ge=1)
    avg_price: str | None = None


class PortfolioImportRequest(BaseModel):
    """Either `holdings` (pre-parsed) OR `raw_text` (server-parsed). One
    is required, both are tolerated (raw_text takes precedence).
    `format` overrides server auto-detection when set."""

    format: str | None = Field(
        default=None,
        description="csv | cdsl_paste — overrides server auto-detection",
    )
    holdings: list[PortfolioHolding] | None = None
    raw_text: str | None = Field(default=None, description="CSV or paste blob")
    name: str = Field(default="My Portfolio", max_length=128)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _validate_tickers(
    session: AsyncSession, holdings: list[ParsedHolding]
) -> tuple[list[ParsedHolding], list[str]]:
    """Filter out tickers not in the active universe. Returns (kept, unknown)."""
    if not holdings:
        return [], []
    tickers = {h.ticker for h in holdings}
    found = (
        await session.execute(
            select(Stock.ticker).where(
                Stock.ticker.in_(tickers), Stock.active.is_(True)
            )
        )
    ).scalars().all()
    found_set = set(found)
    kept = [h for h in holdings if h.ticker in found_set]
    unknown = sorted(tickers - found_set)
    return kept, unknown


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/import")
async def import_portfolio(
    req: PortfolioImportRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Persist a portfolio for the authenticated user. Either `holdings`
    or `raw_text` is required.

    Parse failures are tolerant: rows we can't read are skipped and
    surfaced in `skipped_rows`. Tickers outside the active universe are
    surfaced in `unknown_tickers` (and dropped). Repeated rows for the
    same ticker are merged with weighted-average cost."""
    skipped: list[str] = []
    detected_format: str | None = None

    # Resolve to a list[ParsedHolding].
    if req.raw_text:
        report = parse_text(req.raw_text, format=req.format)
        items = report.holdings
        skipped = report.skipped_rows
        detected_format = report.detected_format
    elif req.holdings:
        items = [
            ParsedHolding(
                ticker=h.ticker.strip().upper(),
                quantity=h.quantity,
                avg_price=Decimal(h.avg_price) if h.avg_price else None,
            )
            for h in req.holdings
        ]
        detected_format = req.format or "json"
    else:
        raise HTTPException(
            status_code=400,
            detail="either `holdings` or `raw_text` is required",
        )

    if not items:
        raise HTTPException(
            status_code=400,
            detail={"reason": "no parseable holdings", "skipped_rows": skipped},
        )

    items = collapse_duplicates(items)

    # Universe gate.
    items, unknown = await _validate_tickers(session, items)
    if not items:
        raise HTTPException(
            status_code=400,
            detail={
                "reason": "none of the tickers are in the active universe",
                "unknown_tickers": unknown,
                "skipped_rows": skipped,
            },
        )

    # Persist. New portfolio per import — keeps history clean.
    portfolio = Portfolio(
        user_id=user.id, name=req.name, source=detected_format
    )
    session.add(portfolio)
    await session.flush()  # populate portfolio.id

    rows = [
        HoldingUser(
            portfolio_id=portfolio.id,
            ticker=h.ticker,
            quantity=h.quantity,
            avg_price=h.avg_price,
        )
        for h in items
    ]
    session.add_all(rows)
    await session.commit()

    total_cost = sum(
        (h.avg_price or Decimal("0")) * h.quantity for h in items
    )
    return {
        "portfolio_id": portfolio.id,
        "n_positions": len(items),
        "total_cost_inr": f"{total_cost:.2f}",
        "format": detected_format,
        "skipped_rows": skipped,
        "unknown_tickers": unknown,
    }


@router.get("/{portfolio_id}/diagnostics")
async def diagnostics(portfolio_id: int) -> dict[str, Any]:
    """STUB — real diagnostics land in P3-A5."""
    out = dict(_DIAG_STUB)
    out["portfolio_id"] = portfolio_id
    out["_stub"] = True
    return out
