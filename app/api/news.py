"""GET /news/{ticker} — recent news with sentiment for one ticker."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.news_service import get_news_for_ticker, refresh_news
from app.db.session import get_session

router = APIRouter(tags=["news"])


@router.get("/news/{ticker}")
async def news(
    ticker: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    hours: int = Query(24, ge=1, le=72),
    limit: int = Query(25, ge=1, le=100),
) -> dict:
    if not ticker or len(ticker) > 32:
        raise HTTPException(status_code=400, detail="invalid ticker")
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="redis unavailable")
    return await get_news_for_ticker(session, redis, ticker, hours=hours, limit=limit)


@router.post("/news/_/refresh")
async def trigger_refresh(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Force a refresh from RSS sources (bypasses 5-min cache)."""
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="redis unavailable")
    await redis.delete("ts:news:last_refresh")
    return await refresh_news(session, redis)
