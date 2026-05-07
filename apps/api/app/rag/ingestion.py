"""Document ingestion pipeline — chunk, embed, and store in Qdrant."""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "concall_transcripts"
_CHUNK_SIZE_TOKENS = 512
_CHUNK_OVERLAP_TOKENS = 64


@dataclass
class DocumentChunk:
    """A single chunk ready for embedding and storage."""
    id: str
    text: str
    metadata: dict[str, Any]


class DocumentIngester:
    """Chunk PDF / text documents, embed with OpenAI or BGE, store in Qdrant.

    Each document is indexed by ticker + date so it can be filtered during
    retrieval.
    """

    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        embedding_model: str = "text-embedding-3-small",
        openai_api_key: str = "",
    ) -> None:
        self._qdrant_url = qdrant_url
        self._embedding_model = embedding_model
        self._openai_api_key = openai_api_key

    async def ingest_pdf(
        self,
        pdf_path: str | Path,
        ticker: str,
        doc_date: str,
        doc_type: str = "concall",
    ) -> int:
        """Extract text from a PDF, chunk it, embed, and store.

        Returns the number of chunks stored.
        """
        text = self._extract_text(pdf_path)
        chunks = self._chunk_text(text, ticker=ticker, doc_date=doc_date, doc_type=doc_type)
        embeddings = await self._embed_chunks([c.text for c in chunks])
        await self._store_in_qdrant(chunks, embeddings)
        logger.info("Ingested %d chunks for %s (%s)", len(chunks), ticker, doc_date)
        return len(chunks)

    async def ingest_text(
        self,
        text: str,
        ticker: str,
        doc_date: str,
        doc_type: str = "concall",
    ) -> int:
        """Chunk raw text, embed, and store. Returns chunk count."""
        chunks = self._chunk_text(text, ticker=ticker, doc_date=doc_date, doc_type=doc_type)
        embeddings = await self._embed_chunks([c.text for c in chunks])
        await self._store_in_qdrant(chunks, embeddings)
        return len(chunks)

    # ------------------------------------------------------------------
    # Text extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(pdf_path: str | Path) -> str:
        """Extract text content from a PDF file."""
        try:
            import fitz  # PyMuPDF  # type: ignore[import-untyped]

            doc = fitz.open(str(pdf_path))
            pages: list[str] = []
            for page in doc:
                pages.append(page.get_text())
            doc.close()
            return "\n\n".join(pages)
        except ImportError:
            logger.error("PyMuPDF (fitz) not installed — cannot extract PDF text")
            raise RuntimeError("PDF extraction requires PyMuPDF: pip install pymupdf")

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    @staticmethod
    def _chunk_text(
        text: str,
        ticker: str,
        doc_date: str,
        doc_type: str,
    ) -> list[DocumentChunk]:
        """Split text into overlapping chunks of ~512 tokens.

        Uses a simple word-based approximation (1 token ~ 0.75 words).
        """
        words = text.split()
        words_per_chunk = int(_CHUNK_SIZE_TOKENS * 0.75)
        overlap_words = int(_CHUNK_OVERLAP_TOKENS * 0.75)
        step = max(words_per_chunk - overlap_words, 1)

        chunks: list[DocumentChunk] = []
        for i in range(0, len(words), step):
            chunk_words = words[i : i + words_per_chunk]
            if not chunk_words:
                break

            chunk_text = " ".join(chunk_words)
            chunk_id = hashlib.sha256(
                f"{ticker}:{doc_date}:{i}".encode()
            ).hexdigest()[:16]

            chunks.append(DocumentChunk(
                id=chunk_id,
                text=chunk_text,
                metadata={
                    "ticker": ticker,
                    "doc_date": doc_date,
                    "doc_type": doc_type,
                    "chunk_index": i // step,
                },
            ))

        return chunks

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    async def _embed_chunks(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using OpenAI's embedding API."""
        import openai

        client = openai.AsyncOpenAI(api_key=self._openai_api_key)

        # Process in batches of 100 (API limit)
        all_embeddings: list[list[float]] = []
        batch_size = 100

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = await client.embeddings.create(
                model=self._embedding_model,
                input=batch,
            )
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    # ------------------------------------------------------------------
    # Qdrant storage
    # ------------------------------------------------------------------

    async def _store_in_qdrant(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> None:
        """Upsert chunk vectors and payloads into Qdrant."""
        from qdrant_client import AsyncQdrantClient
        from qdrant_client.models import PointStruct, VectorParams, Distance

        client = AsyncQdrantClient(url=self._qdrant_url)

        # Ensure collection exists
        collections = await client.get_collections()
        collection_names = [c.name for c in collections.collections]

        if _COLLECTION_NAME not in collection_names:
            vector_size = len(embeddings[0]) if embeddings else 1536
            await client.create_collection(
                collection_name=_COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                ),
            )

        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=emb,
                payload={
                    "text": chunk.text,
                    **chunk.metadata,
                },
            )
            for chunk, emb in zip(chunks, embeddings, strict=True)
        ]

        await client.upsert(
            collection_name=_COLLECTION_NAME,
            points=points,
        )
        await client.close()
