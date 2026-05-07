"""GET /deals/{ticker} — bulk + block deals for one Indian stock."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.deal import Deal
from app.db.session import get_session

router = APIRouter(tags=["deals"])

DealKind = Literal["bulk", "block", "any"]


def _str(d: Decimal | None) -> str | None:
    return str(d) if d is not None else None


def _serialise(r: Deal) -> dict[str, Any]:
    return {
        "trade_date": r.trade_date.isoformat(),
        "symbol": r.symbol,
        "security_name": r.security_name,
        "client_name": r.client_name,
        "side": r.side,
        "quantity": r.quantity,
        "avg_price": _str(r.avg_price),
        "trade_value": _str(r.avg_price * r.quantity if r.avg_price else None),
        "kind": r.kind,
        "remarks": r.remarks,
    }


def _summarise(rows: list[Deal]) -> dict[str, Any]:
    if not rows:
        return {
            "n_deals": 0,
            "n_buys": 0,
            "n_sells": 0,
            "buy_qty": 0,
            "sell_qty": 0,
            "net_qty": 0,
            "buy_value": "0",
            "sell_value": "0",
        }
    buy_qty = sum(r.quantity for r in rows if r.side == "BUY")
    sell_qty = sum(r.quantity for r in rows if r.side == "SELL")
    buy_val = sum((r.avg_price * r.quantity for r in rows if r.side == "BUY"), Decimal(0))
    sell_val = sum((r.avg_price * r.quantity for r in rows if r.side == "SELL"), Decimal(0))
    return {
        "n_deals": len(rows),
        "n_buys": sum(1 for r in rows if r.side == "BUY"),
        "n_sells": sum(1 for r in rows if r.side == "SELL"),
        "buy_qty": buy_qty,
        "sell_qty": sell_qty,
        "net_qty": buy_qty - sell_qty,
        "buy_value": str(buy_val.quantize(Decimal("0.01"))),
        "sell_value": str(sell_val.quantize(Decimal("0.01"))),
    }


@router.get("/deals/{ticker}")
async def deals(
    ticker: str,
    kind: DealKind = Query("any"),
    days: int = Query(90, ge=1, le=365),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not ticker or len(ticker) > 32:
        raise HTTPException(status_code=400, detail="invalid ticker")
    sym = ticker.upper().strip()
    cutoff = date.today() - timedelta(days=days)

    stmt = (
        select(Deal)
        .where(Deal.symbol == sym)
        .where(Deal.trade_date >= cutoff)
        .order_by(desc(Deal.trade_date), desc(Deal.id))
        .limit(limit)
    )
    if kind != "any":
        stmt = stmt.where(Deal.kind == kind)

    rows = (await session.execute(stmt)).scalars().all()

    return {
        "ticker": sym,
        "kind": kind,
        "lookback_days": days,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "summary": _summarise(rows),
        "items": [_serialise(r) for r in rows],
    }
