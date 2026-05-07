"""GET /research/{ticker}?q=... — RAG retrieval over annual reports + notes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import Document
from app.db.session import get_session
from app.rag.embeddings import embed_one
from app.rag.retrieval import search, to_dict

router = APIRouter(tags=["research"])


@router.get("/research/_/coverage")
async def coverage(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Which tickers have at least one ingested document?"""
    rows = (
        await session.execute(
            select(Document.ticker, Document.kind, Document.fy, Document.title, Document.n_chunks)
            .order_by(Document.ticker, Document.kind, Document.fy)
        )
    ).all()
    return {
        "n_documents": len(rows),
        "tickers": sorted({r[0] for r in rows}),
        "documents": [
            {"ticker": r[0], "kind": r[1], "fy": r[2], "title": r[3], "n_chunks": r[4]}
            for r in rows
        ],
    }


@router.get("/research/{ticker}")
async def research(
    ticker: str,
    request: Request,
    q: str = Query(..., min_length=2, max_length=500),
    top_k: int = Query(5, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not ticker or len(ticker) > 32:
        raise HTTPException(status_code=400, detail="invalid ticker")
    sym = ticker.upper().strip()

    redis = getattr(request.app.state, "redis", None)
    try:
        query_embedding = await embed_one(q, redis=redis)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"embedding failed: {e}") from e

    hits = await search(session, ticker=sym, query_embedding=query_embedding, top_k=top_k)
    return {
        "ticker": sym,
        "query": q,
        "top_k": top_k,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "n_hits": len(hits),
        "hits": [to_dict(h) for h in hits],
    }
