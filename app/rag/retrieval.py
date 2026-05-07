"""Retrieval over `document_chunks` using NumPy cosine similarity.

Why numpy and not pgvector? Our demo corpus is small (≤ 10 docs × ~80
chunks). A single SELECT pulls everything for a ticker; `np.dot` over a
2D matrix is sub-millisecond at this size, and we sidestep the pgvector
bottle-vs-postgres-version mismatch on Homebrew. The stored shape is
`JSONB list[float]` — drop-in replaceable with pgvector later.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import Document, DocumentChunk

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RetrievedChunk:
    document_id: int
    document_title: str
    document_kind: str
    document_fy: str | None
    chunk_idx: int
    page: int | None
    text: str
    score: float            # cosine similarity in [-1, 1]; higher = closer


def cosine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Row-wise cosine similarity between query (1D) and matrix (2D)."""
    if b.size == 0:
        return np.array([], dtype=np.float32)
    a_norm = np.linalg.norm(a)
    b_norms = np.linalg.norm(b, axis=1)
    denom = a_norm * b_norms
    safe = np.where(denom > 0, denom, 1.0)
    return (b @ a) / safe


async def search(
    session: AsyncSession,
    *,
    ticker: str,
    query_embedding: list[float],
    top_k: int = 5,
    kinds: list[str] | None = None,
) -> list[RetrievedChunk]:
    """Cosine-rank chunks for one ticker. Returns top_k descending."""
    sym = ticker.upper().strip()
    stmt = (
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.ticker == sym)
        .where(DocumentChunk.embedding.isnot(None))
    )
    if kinds:
        stmt = stmt.where(Document.kind.in_(kinds))

    rows = (await session.execute(stmt)).all()
    if not rows:
        return []

    q = np.asarray(query_embedding, dtype=np.float32)
    if q.size == 0:
        return []

    chunk_objs: list[DocumentChunk] = []
    docs: list[Document] = []
    embeds: list[list[float]] = []
    for chunk, doc in rows:
        if chunk.embedding is None:
            continue
        chunk_objs.append(chunk)
        docs.append(doc)
        embeds.append(chunk.embedding)

    if not embeds:
        return []

    matrix = np.asarray(embeds, dtype=np.float32)
    scores = cosine(q, matrix)
    # argsort descending
    order = np.argsort(-scores)
    out: list[RetrievedChunk] = []
    for i in order[:top_k]:
        c = chunk_objs[i]
        d = docs[i]
        out.append(
            RetrievedChunk(
                document_id=d.id,
                document_title=d.title,
                document_kind=d.kind,
                document_fy=d.fy,
                chunk_idx=c.chunk_idx,
                page=c.page,
                text=c.text,
                score=float(scores[i]),
            )
        )
    return out


def to_dict(rc: RetrievedChunk) -> dict:
    return {
        "document_id": rc.document_id,
        "document_title": rc.document_title,
        "document_kind": rc.document_kind,
        "document_fy": rc.document_fy,
        "chunk_idx": rc.chunk_idx,
        "page": rc.page,
        "text": rc.text,
        "score": round(rc.score, 4),
    }


def stamp_now() -> str:
    return datetime.now(timezone.utc).isoformat()
