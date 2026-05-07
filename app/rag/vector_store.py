"""Vector-store abstraction.

Two implementations behind a single interface:

  * `JsonbStore` (default) — embeddings live in `document_chunks.embedding`
    (JSONB) and we rank with numpy cosine. Sub-millisecond at our demo
    scale (≤ 800 vectors), zero new dependencies.

  * `PineconeStore` (when `VECTOR_BACKEND=pinecone` + `PINECONE_API_KEY`
    set) — embeddings get upserted into a Pinecone serverless index. The
    text + metadata stay in Postgres, so retrieval is two-step:
      1. Pinecone returns {id, score} for top-K
      2. We resolve back to `DocumentChunk` rows by `(document_id, chunk_idx)`

Both implementations return the same `RetrievedChunk` shape, so callers
(API endpoint, LLM tool) don't care which is active.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.document import Document, DocumentChunk
from app.rag.retrieval import RetrievedChunk, cosine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class VectorStore(ABC):
    """Backend-agnostic ops the RAG layer uses."""

    name: str  # for logging / admin trail

    @abstractmethod
    async def upsert(
        self,
        *,
        document_id: int,
        chunks: list[tuple[int, list[float], dict[str, Any]]],
        ticker: str,
    ) -> int:
        """Upsert (chunk_idx, embedding, metadata) tuples for one document.
        Returns number of vectors written."""

    @abstractmethod
    async def search(
        self,
        session: AsyncSession,
        *,
        ticker: str,
        query_embedding: list[float],
        top_k: int,
        kinds: list[str] | None,
    ) -> list[RetrievedChunk]:
        """Return top-K most-similar chunks (descending score)."""


# ---------------------------------------------------------------------------
# JSONB backend (numpy cosine over Postgres rows)
# ---------------------------------------------------------------------------


class JsonbStore(VectorStore):
    name = "jsonb"

    async def upsert(
        self,
        *,
        document_id: int,
        chunks: list[tuple[int, list[float], dict[str, Any]]],
        ticker: str,
    ) -> int:
        # The worker writes the JSONB embedding directly via the ORM. This
        # method is a no-op so callers can write generic code that always
        # calls `vector_store.upsert(...)` regardless of backend.
        return len(chunks)

    async def search(
        self,
        session: AsyncSession,
        *,
        ticker: str,
        query_embedding: list[float],
        top_k: int,
        kinds: list[str] | None,
    ) -> list[RetrievedChunk]:
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
        order = np.argsort(-scores)[:top_k]
        out: list[RetrievedChunk] = []
        for i in order:
            c = chunk_objs[i]
            d = docs[i]
            out.append(
                RetrievedChunk(
                    document_id=d.id, document_title=d.title, document_kind=d.kind,
                    document_fy=d.fy, chunk_idx=c.chunk_idx, page=c.page,
                    text=c.text, score=float(scores[i]),
                )
            )
        return out


# ---------------------------------------------------------------------------
# Pinecone backend (serverless, one index, per-ticker namespace)
# ---------------------------------------------------------------------------


class PineconeStore(VectorStore):
    """Pinecone serverless backend.

    Strategy:
      * One index, name from `PINECONE_INDEX_NAME` (default "mr-market").
        Created lazily on first use; metric=cosine, dim=1536.
      * Per-ticker **namespace** so we don't pay the filter cost on every
        query — sym → namespace.
      * Vector ID = `{document_id}:{chunk_idx}` so we can resolve back to
        the Postgres row for the full text.
      * Metadata kept tiny (kind, fy, document_id, chunk_idx, page) — the
        text + author / source-url stays in Postgres.
    """

    name = "pinecone"

    def __init__(self) -> None:
        self._client: Any | None = None
        self._index: Any | None = None

    def _ensure_index(self) -> Any:
        """Lazily build the client + ensure the index exists."""
        if self._index is not None:
            return self._index

        settings = get_settings()
        if not settings.pinecone_api_key:
            raise RuntimeError(
                "Pinecone backend selected but PINECONE_API_KEY is empty."
            )

        from pinecone import Pinecone, ServerlessSpec

        pc = Pinecone(api_key=settings.pinecone_api_key)
        existing_names = {ix["name"] for ix in pc.list_indexes()}
        if settings.pinecone_index_name not in existing_names:
            logger.info(
                "Pinecone: creating serverless index %s in %s/%s",
                settings.pinecone_index_name,
                settings.pinecone_cloud,
                settings.pinecone_region,
            )
            pc.create_index(
                name=settings.pinecone_index_name,
                dimension=1536,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud=settings.pinecone_cloud, region=settings.pinecone_region
                ),
            )
        self._client = pc
        self._index = pc.Index(settings.pinecone_index_name)
        return self._index

    @staticmethod
    def _vector_id(document_id: int, chunk_idx: int) -> str:
        return f"{document_id}:{chunk_idx}"

    @staticmethod
    def _namespace(ticker: str) -> str:
        return ticker.upper().strip() or "_default"

    async def upsert(
        self,
        *,
        document_id: int,
        chunks: list[tuple[int, list[float], dict[str, Any]]],
        ticker: str,
    ) -> int:
        if not chunks:
            return 0
        index = self._ensure_index()
        ns = self._namespace(ticker)
        vectors = [
            {
                "id": self._vector_id(document_id, chunk_idx),
                "values": embedding,
                "metadata": {
                    **{k: v for k, v in metadata.items() if v is not None},
                    "document_id": document_id,
                    "chunk_idx": chunk_idx,
                    "ticker": ticker.upper(),
                },
            }
            for (chunk_idx, embedding, metadata) in chunks
        ]
        # Pinecone's default upsert batch limit is 100 vectors / 2 MB.
        BATCH = 100
        written = 0
        for i in range(0, len(vectors), BATCH):
            res = index.upsert(vectors=vectors[i : i + BATCH], namespace=ns)
            written += int(res.get("upserted_count", len(vectors[i : i + BATCH])))
        return written

    async def search(
        self,
        session: AsyncSession,
        *,
        ticker: str,
        query_embedding: list[float],
        top_k: int,
        kinds: list[str] | None,
    ) -> list[RetrievedChunk]:
        index = self._ensure_index()
        ns = self._namespace(ticker)
        flt: dict[str, Any] | None = None
        if kinds:
            flt = {"kind": {"$in": list(kinds)}}

        res = index.query(
            namespace=ns,
            vector=query_embedding,
            top_k=max(1, min(top_k, 100)),
            include_metadata=True,
            filter=flt,
        )
        matches = res.get("matches") or []
        if not matches:
            return []

        # Resolve metadata + full text back from Postgres in ONE query.
        wanted: list[tuple[int, int]] = []
        score_by_key: dict[tuple[int, int], float] = {}
        for m in matches:
            md = m.get("metadata") or {}
            try:
                key = (int(md["document_id"]), int(md["chunk_idx"]))
            except (KeyError, TypeError, ValueError):
                continue
            wanted.append(key)
            score_by_key[key] = float(m.get("score", 0.0))

        if not wanted:
            return []
        doc_ids = list({d for d, _ in wanted})

        rows = (
            await session.execute(
                select(DocumentChunk, Document)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(DocumentChunk.document_id.in_(doc_ids))
            )
        ).all()
        by_key: dict[tuple[int, int], tuple[DocumentChunk, Document]] = {
            (c.document_id, c.chunk_idx): (c, d) for c, d in rows
        }

        out: list[RetrievedChunk] = []
        # Preserve Pinecone's score ordering.
        for k in wanted:
            pair = by_key.get(k)
            if pair is None:
                continue
            c, d = pair
            out.append(
                RetrievedChunk(
                    document_id=d.id, document_title=d.title, document_kind=d.kind,
                    document_fy=d.fy, chunk_idx=c.chunk_idx, page=c.page,
                    text=c.text, score=score_by_key[k],
                )
            )
        return out


# ---------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------


def get_store() -> VectorStore:
    """Pick the backend based on settings, with a graceful fall-back."""
    s = get_settings()
    backend = (s.vector_backend or "jsonb").lower()
    if backend == "pinecone":
        if not s.pinecone_api_key:
            logger.warning(
                "VECTOR_BACKEND=pinecone but PINECONE_API_KEY is empty — "
                "falling back to JSONB."
            )
            return JsonbStore()
        return PineconeStore()
    return JsonbStore()
