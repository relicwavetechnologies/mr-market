"""Portfolio REST endpoints (P3-A4 import + P3-A5 diagnostics).

Both endpoints are now real:
- `POST /portfolio/import` — auth-gated; CSV / CDSL paste / pre-parsed.
- `GET /portfolio/{id}/diagnostics` — auth-gated; runs
  `app/analytics/portfolio.py::compute_diagnostics` against live quotes
  + yfinance beta/div-yield + 1-year `prices_daily` history. The `_stub`
  marker is gone.

Schemas locked in `app/contracts/phase3.md`.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.portfolio import Position, compute_diagnostics
from app.api.deps import get_current_user
from app.data.info_service import get_info
from app.data.portfolio_import import (
    ParsedHolding,
    collapse_duplicates,
    parse_text,
)
from app.data.quote_service import get_quote
from app.db.models import HoldingUser, Portfolio, PriceDaily, Stock, User
from app.db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _to_decimal(v: object) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


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
async def diagnostics(
    portfolio_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Run diagnostics over the authenticated user's portfolio. Live
    quotes via the existing get_quote/info pipelines (parallelised),
    1-year drawdown computed from `prices_daily`."""
    portfolio = await session.get(Portfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    if portfolio.user_id != user.id:
        # Don't leak existence — mirror 404 semantics.
        raise HTTPException(status_code=404, detail="portfolio not found")

    holdings = (
        await session.execute(
            select(HoldingUser).where(HoldingUser.portfolio_id == portfolio_id)
        )
    ).scalars().all()
    if not holdings:
        raise HTTPException(status_code=400, detail="portfolio has no positions")

    tickers = [h.ticker for h in holdings]

    # Stock metadata (sector lookup) — single DB hop.
    stock_rows = (
        await session.execute(select(Stock).where(Stock.ticker.in_(tickers)))
    ).scalars().all()
    sector_map: dict[str, str | None] = {s.ticker: s.sector for s in stock_rows}

    redis = request.app.state.redis

    # Live quotes — fan out in parallel; Redis cache absorbs duplicates.
    async def _quote(t: str) -> tuple[str, Decimal | None]:
        try:
            q = await get_quote(t, redis, session)
            return t, _to_decimal(q.get("price"))
        except Exception as e:  # noqa: BLE001
            logger.warning("get_quote failed for %s: %s", t, e)
            return t, None

    # yfinance info — beta + div_yield (parallel + cached).
    async def _info(t: str) -> tuple[str, dict[str, Any] | None]:
        try:
            info = await get_info(session, t)
            return t, info
        except Exception as e:  # noqa: BLE001
            logger.warning("get_info failed for %s: %s", t, e)
            return t, None

    quotes = dict(await asyncio.gather(*[_quote(t) for t in tickers]))
    infos = dict(await asyncio.gather(*[_info(t) for t in tickers]))

    beta_map: dict[str, Decimal | None] = {}
    div_yield_map: dict[str, Decimal | None] = {}
    for t in tickers:
        info = (infos.get(t) or {}).get("yfinance") or {}
        beta_map[t] = _to_decimal(info.get("beta"))
        div_yield_map[t] = _to_decimal(info.get("dividend_yield"))

    # 1-year price history from prices_daily (per ticker).
    cutoff = dt.date.today() - dt.timedelta(days=365)
    history_rows = (
        await session.execute(
            select(PriceDaily.ticker, PriceDaily.ts, PriceDaily.close)
            .where(PriceDaily.ticker.in_(tickers))
            .where(PriceDaily.ts >= cutoff)
            .order_by(PriceDaily.ticker, PriceDaily.ts)
        )
    ).all()
    price_history: dict[str, list[tuple[str, Decimal]]] = {t: [] for t in tickers}
    for ticker, ts, close in history_rows:
        if close is None:
            continue
        d = ts.date() if hasattr(ts, "date") else ts
        price_history[ticker].append((d.isoformat(), close))

    positions = [
        Position(
            ticker=h.ticker,
            quantity=int(h.quantity),
            avg_price=h.avg_price,
            current_price=quotes.get(h.ticker),
        )
        for h in holdings
    ]

    diagnostics_out = compute_diagnostics(
        positions,
        sector_map=sector_map,
        beta_map=beta_map,
        div_yield_map=div_yield_map,
        price_history=price_history,
    )
    diagnostics_out["portfolio_id"] = portfolio_id
    diagnostics_out["as_of"] = dt.date.today().isoformat()
    return diagnostics_out
