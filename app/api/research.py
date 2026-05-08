"""GET /research/{ticker}?q=... — RAG retrieval over annual reports + notes.

POST /research/upload — drag-drop PDF ingestion (Phase-3 follow-up).
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Stock, User
from app.db.models.document import Document
from app.db.session import get_session
from app.rag.embeddings import embed_one
from app.rag.retrieval import to_dict
from app.rag.vector_store import get_store
from app.workers.research_ingest import ingest_pdf

logger = logging.getLogger(__name__)

router = APIRouter(tags=["research"])

# Reasonable cap so an accidentally massive PDF can't OOM the box.
# Annual reports are typically 10-50 MB; cap at 50 MB.
MAX_PDF_SIZE_MB = 50
MAX_PDF_SIZE_BYTES = MAX_PDF_SIZE_MB * 1024 * 1024
ALLOWED_KINDS = {"annual_report", "concall_transcript", "research_note", "other"}


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

    store = get_store()
    hits = await store.search(
        session, ticker=sym, query_embedding=query_embedding, top_k=top_k, kinds=None
    )
    return {
        "ticker": sym,
        "query": q,
        "top_k": top_k,
        "backend": store.name,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "n_hits": len(hits),
        "hits": [to_dict(h) for h in hits],
    }


# ---------------------------------------------------------------------------
# Drag-drop ingest — auth-gated multipart upload that flows through the same
# ingest pipeline `scripts.ingest_research` uses. Re-running with the same
# (ticker, kind, fy) replaces the chunks (idempotent re-ingest).
# ---------------------------------------------------------------------------


@router.post("/research/upload")
async def upload_research(
    request: Request,
    ticker: str = Form(..., description="NSE ticker (RELIANCE, TCS, ...)"),
    title: str = Form(..., description="Human title — 'Reliance AR FY25' etc."),
    fy: str | None = Form(default=None),
    kind: str = Form(default="annual_report"),
    source_url: str | None = Form(default=None),
    file: UploadFile = File(..., description="PDF file"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Upload + ingest a PDF for one ticker. Auth-required.

    The flow:
    1. Validate ticker (must be in active universe).
    2. Validate file (PDF mime-type, size ≤ 50 MB).
    3. Stream to a temp file (so the existing `ingest_pdf` worker can
       use a `Path`).
    4. Run `ingest_pdf` — same code path as `scripts.ingest_research`.
       Extracts text, chunks, embeds (text-embedding-3-small), upserts
       to the vector store (Pinecone or JSONB fallback).
    5. Return ingest stats — caller updates UI optimistically.

    Re-uploading with the same (ticker, kind, fy) replaces all chunks
    cleanly (the worker handles dedupe).
    """
    sym = ticker.upper().strip()

    # 1. Universe gate.
    stock = await session.get(Stock, sym)
    if stock is None or not stock.active:
        raise HTTPException(
            status_code=404,
            detail=f"{sym!r} not in active NIFTY-100 universe",
        )

    # 2. Format gate.
    if kind not in ALLOWED_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"kind must be one of {sorted(ALLOWED_KINDS)}",
        )
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="upload must be a .pdf file")
    # FastAPI's UploadFile mime is best-effort — we'll trust the suffix
    # plus pypdf's parse-error path for the actual content check.

    # 3. Stream to a temp file with a size cap.
    suffix = Path(file.filename).suffix or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        total = 0
        try:
            while True:
                chunk = await file.read(1024 * 1024)  # 1 MB at a time
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_PDF_SIZE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"PDF too large (> {MAX_PDF_SIZE_MB} MB)",
                    )
                tmp.write(chunk)
        except HTTPException:
            tmp_path.unlink(missing_ok=True)
            raise
        except Exception as e:  # noqa: BLE001
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=500, detail=f"upload failed: {e!s}"
            ) from e

    if total == 0:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="empty file")

    # 4. Run ingest. Reuse the same worker `scripts.ingest_research` uses.
    redis = getattr(request.app.state, "redis", None)
    try:
        stats = await ingest_pdf(
            session,
            ticker=sym,
            pdf_path=tmp_path,
            title=title.strip(),
            kind=kind,
            fy=(fy or "").strip() or None,
            source_url=(source_url or "").strip() or None,
            redis=redis,
        )
    finally:
        # Always clean up the temp file — ingest_pdf has already extracted + chunked.
        tmp_path.unlink(missing_ok=True)

    if stats.error:
        # The ingest worker reports parse / embed / upsert failures
        # in `stats.error`. Surface that to the caller so the UI can
        # show a meaningful message.
        return {
            "ok": False,
            "ticker": sym,
            "title": title,
            "fy": fy,
            "kind": kind,
            "n_pages": stats.n_pages,
            "n_chunks": stats.n_chunks,
            "n_embedded": stats.n_embedded,
            "duration_ms": stats.duration_ms,
            "size_bytes": total,
            "error": stats.error,
            "uploaded_by": str(user.id),
        }

    return {
        "ok": True,
        "ticker": sym,
        "title": title,
        "fy": fy,
        "kind": kind,
        "n_pages": stats.n_pages,
        "n_chunks": stats.n_chunks,
        "n_embedded": stats.n_embedded,
        "duration_ms": stats.duration_ms,
        "size_bytes": total,
        "uploaded_by": str(user.id),
    }
