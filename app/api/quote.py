"""GET /quote/{ticker} — triangulated quote endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.info_service import get_info
from app.data.quote_service import SOURCES, get_quote
from app.db.session import get_session

router = APIRouter(tags=["quote"])


@router.get("/quote/{ticker}")
async def quote(
    ticker: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    skip_cache: bool = Query(False, description="Bypass Redis cache"),
) -> dict:
    if not ticker or len(ticker) > 32:
        raise HTTPException(status_code=400, detail="invalid ticker")
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="redis unavailable")
    return await get_quote(ticker, redis, session, skip_cache=skip_cache)


@router.get("/quote/{ticker}/info")
async def quote_info(
    ticker: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not ticker or len(ticker) > 32:
        raise HTTPException(status_code=400, detail="invalid ticker")
    return await get_info(session, ticker)


@router.get("/quote/_/sources")
async def list_sources() -> dict:
    """Static — what sources we triangulate against."""
    return {"sources": list(SOURCES.keys())}
