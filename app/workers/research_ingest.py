"""Ingest a single document (PDF) into the RAG corpus.

Pipeline:
  1. Extract per-page text via pypdf.
  2. Chunk with fixed window + overlap.
  3. Embed each chunk via OpenAI text-embedding-3-small.
  4. Upsert (document, chunks) — idempotent on (ticker, kind, fy).

Each chunk is stored with `embedding` as JSONB; retrieval uses numpy
cosine over the SELECT result set (see app/rag/retrieval.py).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from redis import asyncio as aioredis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import Document, DocumentChunk
from app.db.models.scrape_log import ScrapeLog
from app.rag.chunking import chunk_pages, extract_pages
from app.rag.embeddings import EMBEDDING_MODEL, embed_batch

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestStats:
    ticker: str
    kind: str
    fy: str | None
    n_pages: int = 0
    n_chunks: int = 0
    n_embedded: int = 0
    duration_ms: int = 0
    error: str | None = None

    def to_meta(self) -> dict:
        return {
            "ticker": self.ticker,
            "kind": self.kind,
            "fy": self.fy,
            "n_pages": self.n_pages,
            "n_chunks": self.n_chunks,
            "n_embedded": self.n_embedded,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


async def ingest_pdf(
    session: AsyncSession,
    *,
    ticker: str,
    pdf_path: Path,
    title: str,
    kind: str = "annual_report",
    fy: str | None = None,
    source_url: str | None = None,
    redis: aioredis.Redis | None = None,
) -> IngestStats:
    started = time.perf_counter()
    sym = ticker.upper().strip()
    stats = IngestStats(ticker=sym, kind=kind, fy=fy)

    if not pdf_path.is_file():
        stats.error = f"file not found: {pdf_path}"
        stats.duration_ms = int((time.perf_counter() - started) * 1000)
        await _audit(session, stats, ok=False)
        return stats

    # 1. Parse PDF.
    try:
        pages = extract_pages(pdf_path)
    except Exception as e:  # noqa: BLE001
        stats.error = f"pdf_parse: {e}"
        stats.duration_ms = int((time.perf_counter() - started) * 1000)
        await _audit(session, stats, ok=False)
        return stats

    stats.n_pages = len(pages)
    if not pages:
        stats.error = "no extractable text"
        stats.duration_ms = int((time.perf_counter() - started) * 1000)
        await _audit(session, stats, ok=False)
        return stats

    # 2. Chunk.
    chunks = chunk_pages(pages)
    stats.n_chunks = len(chunks)

    # 3. Embed.
    try:
        embeddings = await embed_batch([c.text for c in chunks], redis=redis)
    except Exception as e:  # noqa: BLE001
        stats.error = f"embed: {e}"
        stats.duration_ms = int((time.perf_counter() - started) * 1000)
        await _audit(session, stats, ok=False)
        return stats
    stats.n_embedded = len(embeddings)

    # 4. Upsert.
    existing = (
        await session.execute(
            select(Document).where(
                Document.ticker == sym, Document.kind == kind, Document.fy == fy
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Replace chunks for this document (idempotent re-ingest).
        await session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == existing.id)
        )
        existing.title = title
        existing.source_url = source_url
        existing.source_path = str(pdf_path)
        existing.n_pages = stats.n_pages
        existing.n_chunks = stats.n_chunks
        existing.embedding_model = EMBEDDING_MODEL
        document_id = existing.id
    else:
        doc = Document(
            ticker=sym,
            kind=kind,
            title=title,
            fy=fy,
            source_url=source_url,
            source_path=str(pdf_path),
            n_pages=stats.n_pages,
            n_chunks=stats.n_chunks,
            embedding_model=EMBEDDING_MODEL,
        )
        session.add(doc)
        await session.flush()  # populate doc.id
        document_id = doc.id

    for c, vec in zip(chunks, embeddings, strict=True):
        session.add(
            DocumentChunk(
                document_id=document_id,
                chunk_idx=c.chunk_idx,
                page=c.page,
                text=c.text,
                embedding=list(vec),
                n_tokens=c.token_estimate,
                meta={"pages_spanned": list(c.pages_spanned), "char_count": c.char_count},
            )
        )

    await session.commit()
    stats.duration_ms = int((time.perf_counter() - started) * 1000)
    await _audit(session, stats, ok=True)
    return stats


async def _audit(session: AsyncSession, stats: IngestStats, *, ok: bool) -> None:
    try:
        session.add(
            ScrapeLog(
                source="research_ingest",
                ok=ok,
                duration_ms=stats.duration_ms,
                error=stats.error,
                meta=stats.to_meta(),
            )
        )
        await session.commit()
    except Exception:  # noqa: BLE001
        await session.rollback()
