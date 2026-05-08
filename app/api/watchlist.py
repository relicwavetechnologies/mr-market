"""Per-user watchlist endpoints (P3-A7).

`/watchlist` is now real: persisted in the `watchlist` table per
authenticated user. The `_stub: true` marker is gone. Daily-digest
cron lives in `app/workers/watchlist_digest.py`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Stock, User, Watchlist
from app.db.session import get_session

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class WatchlistAddRequest(BaseModel):
    ticker: str


async def _list_for_user(
    session: AsyncSession, user_id
) -> list[str]:
    rows = (
        await session.execute(
            select(Watchlist.ticker)
            .where(Watchlist.user_id == user_id)
            .order_by(Watchlist.ticker)
        )
    ).scalars().all()
    return list(rows)


@router.get("")
async def list_watchlist(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    tickers = await _list_for_user(session, user.id)
    return {"ok": True, "tickers": tickers, "size": len(tickers)}


@router.post("")
async def add_to_watchlist(
    req: WatchlistAddRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    sym = req.ticker.strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="ticker required")

    # Validate against active universe.
    stock = await session.get(Stock, sym)
    if stock is None or not stock.active:
        raise HTTPException(
            status_code=404,
            detail=f"{sym!r} not in active NIFTY-100 universe",
        )

    # Idempotent insert.
    stmt = insert(Watchlist).values(user_id=user.id, ticker=sym)
    stmt = stmt.on_conflict_do_nothing(index_elements=["user_id", "ticker"])
    await session.execute(stmt)
    await session.commit()

    tickers = await _list_for_user(session, user.id)
    return {"ok": True, "tickers": tickers, "size": len(tickers)}


@router.delete("/{ticker}")
async def remove_from_watchlist(
    ticker: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    sym = ticker.strip().upper()
    res = await session.execute(
        delete(Watchlist)
        .where(Watchlist.user_id == user.id)
        .where(Watchlist.ticker == sym)
    )
    await session.commit()
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"{sym!r} not in watchlist")
    tickers = await _list_for_user(session, user.id)
    return {"ok": True, "tickers": tickers, "size": len(tickers)}
