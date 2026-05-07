"""Document ingestion pipeline — annual reports and concall transcripts.

Ingests PDF documents (annual reports, concall transcripts), extracts
text using PyMuPDF, chunks into 512-token segments, generates embeddings
(BGE or OpenAI), and stores vectors in Qdrant for semantic search.
Indexed by ticker and date for filtered retrieval.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Chunk size in tokens (approximate — we use word-based splitting
# with ~1.3 words per token as a conservative estimate)
CHUNK_SIZE_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 64
WORDS_PER_TOKEN = 1.3  # conservative; actual for English is ~0.75

# Qdrant collection name
QDRANT_COLLECTION = "mr_market_documents"

# Embedding model options
EMBEDDING_MODEL_BGE = "BAAI/bge-base-en-v1.5"
EMBEDDING_MODEL_OPENAI = "text-embedding-3-small"


@dataclass
class DocumentChunk:
    """A single chunk of a document for vector indexing."""

    chunk_id: str
    ticker: str
    document_type: str  # "annual_report" | "concall_transcript"
    document_date: str  # ISO date
    page_number: int
    chunk_index: int
    text: str
    embedding: list[float] = field(default_factory=list)

    def to_qdrant_payload(self) -> dict[str, Any]:
        """Build a Qdrant-compatible payload dict."""
        return {
            "ticker": self.ticker,
            "document_type": self.document_type,
            "document_date": self.document_date,
            "page_number": self.page_number,
            "chunk_index": self.chunk_index,
            "text": self.text,
        }


class DataIngestionPipeline:
    """Ingests PDF documents, chunks text, embeds, and stores in Qdrant.

    Usage::

        pipeline = DataIngestionPipeline(embedding_backend="bge")
        chunks = await pipeline.run(
            pdf_path="/data/reports/RELIANCE_AR_2025.pdf",
            ticker="RELIANCE",
            document_type="annual_report",
            document_date="2025-03-31",
        )
    """

    def __init__(
        self,
        embedding_backend: str = "bge",
        qdrant_url: str | None = None,
        qdrant_api_key: str | None = None,
        chunk_size: int = CHUNK_SIZE_TOKENS,
        chunk_overlap: int = CHUNK_OVERLAP_TOKENS,
    ) -> None:
        self.embedding_backend = embedding_backend
        self.qdrant_url = qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self.qdrant_api_key = qdrant_api_key or os.getenv("QDRANT_API_KEY")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._embedder: _BaseEmbedder | None = None

    # ------------------------------------------------------------------
    # PDF text extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_text_from_pdf(pdf_path: str | Path) -> list[dict[str, Any]]:
        """Extract text from a PDF file using PyMuPDF.

        Returns a list of dicts with ``page_number`` and ``text`` keys.
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        pages: list[dict[str, Any]] = []
        with fitz.open(str(path)) as doc:
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text("text")
                if text.strip():
                    pages.append({
                        "page_number": page_num + 1,
                        "text": text.strip(),
                    })

        logger.info("ingestion: extracted %d pages from %s", len(pages), path.name)
        return pages

    # ------------------------------------------------------------------
    # Text chunking
    # ------------------------------------------------------------------

    def chunk_text(
        self,
        text: str,
        ticker: str,
        document_type: str,
        document_date: str,
        page_number: int,
    ) -> list[DocumentChunk]:
        """Split text into overlapping chunks of ~512 tokens.

        Uses word-based splitting with the configured overlap.
        """
        words = text.split()
        chunk_words = int(self.chunk_size * WORDS_PER_TOKEN)
        overlap_words = int(self.chunk_overlap * WORDS_PER_TOKEN)
        step = max(chunk_words - overlap_words, 1)

        chunks: list[DocumentChunk] = []
        for i in range(0, len(words), step):
            chunk_text = " ".join(words[i : i + chunk_words])
            if not chunk_text.strip():
                continue
            chunks.append(
                DocumentChunk(
                    chunk_id=str(uuid.uuid4()),
                    ticker=ticker,
                    document_type=document_type,
                    document_date=document_date,
                    page_number=page_number,
                    chunk_index=len(chunks),
                    text=chunk_text,
                )
            )
            # Stop if we've consumed all words
            if i + chunk_words >= len(words):
                break

        return chunks

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    def _get_embedder(self) -> _BaseEmbedder:
        """Lazily initialise the embedding backend."""
        if self._embedder is not None:
            return self._embedder

        if self.embedding_backend == "openai":
            self._embedder = _OpenAIEmbedder()
        else:
            self._embedder = _BGEEmbedder()

        return self._embedder

    async def embed_chunks(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        """Generate embeddings for all chunks."""
        embedder = self._get_embedder()
        texts = [c.text for c in chunks]
        embeddings = await embedder.embed_batch(texts)
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            chunk.embedding = embedding
        logger.info("ingestion: embedded %d chunks via %s", len(chunks), self.embedding_backend)
        return chunks

    # ------------------------------------------------------------------
    # Qdrant storage
    # ------------------------------------------------------------------

    async def store_in_qdrant(self, chunks: list[DocumentChunk]) -> int:
        """Store embedded chunks in Qdrant vector database."""
        try:
            from qdrant_client import QdrantClient  # type: ignore[import-untyped]
            from qdrant_client.models import Distance, PointStruct, VectorParams  # type: ignore[import-untyped]
        except ImportError:
            logger.error("ingestion: qdrant-client not installed")
            return 0

        client = QdrantClient(url=self.qdrant_url, api_key=self.qdrant_api_key)

        # Ensure collection exists
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]
        if QDRANT_COLLECTION not in collection_names:
            dimension = len(chunks[0].embedding) if chunks else 768
            client.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
            )
            logger.info("ingestion: created Qdrant collection %s", QDRANT_COLLECTION)

        # Upsert points
        points = [
            PointStruct(
                id=chunk.chunk_id,
                vector=chunk.embedding,
                payload=chunk.to_qdrant_payload(),
            )
            for chunk in chunks
            if chunk.embedding
        ]

        if points:
            client.upsert(collection_name=QDRANT_COLLECTION, points=points)
            logger.info("ingestion: stored %d vectors in Qdrant", len(points))

        return len(points)

    # ------------------------------------------------------------------
    # Pipeline entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        pdf_path: str | Path,
        ticker: str,
        document_type: str,
        document_date: str,
    ) -> list[DocumentChunk]:
        """Execute the full ingestion pipeline.

        1. Extract text from PDF.
        2. Chunk into 512-token segments.
        3. Generate embeddings.
        4. Store in Qdrant indexed by ticker + date.

        Returns the list of processed document chunks.
        """
        logger.info(
            "ingestion: starting pipeline for %s (%s, %s)",
            ticker,
            document_type,
            document_date,
        )

        # Extract
        pages = self.extract_text_from_pdf(pdf_path)

        # Chunk
        all_chunks: list[DocumentChunk] = []
        for page in pages:
            chunks = self.chunk_text(
                text=page["text"],
                ticker=ticker,
                document_type=document_type,
                document_date=document_date,
                page_number=page["page_number"],
            )
            all_chunks.extend(chunks)

        logger.info("ingestion: created %d chunks from %d pages", len(all_chunks), len(pages))

        # Embed
        all_chunks = await self.embed_chunks(all_chunks)

        # Store
        stored = await self.store_in_qdrant(all_chunks)

        logger.info(
            "ingestion: pipeline complete — %d chunks, %d stored in Qdrant",
            len(all_chunks),
            stored,
        )
        return all_chunks


# ======================================================================
# Embedding backends (internal)
# ======================================================================


class _BaseEmbedder:
    """Abstract embedding backend."""

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class _BGEEmbedder(_BaseEmbedder):
    """BGE embedding model from HuggingFace (BAAI/bge-base-en-v1.5)."""

    def __init__(self) -> None:
        self._model: Any = None
        self._tokenizer: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoModel, AutoTokenizer  # type: ignore[import-untyped]

        logger.info("ingestion: loading BGE embedding model")
        self._tokenizer = AutoTokenizer.from_pretrained(EMBEDDING_MODEL_BGE)
        self._model = AutoModel.from_pretrained(EMBEDDING_MODEL_BGE)
        self._model.eval()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        import torch

        self._load()
        assert self._tokenizer is not None and self._model is not None

        encoded = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        with torch.no_grad():
            outputs = self._model(**encoded)
            # Use CLS token embedding
            embeddings = outputs.last_hidden_state[:, 0, :]
            # Normalize
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

        return embeddings.tolist()


class _OpenAIEmbedder(_BaseEmbedder):
    """OpenAI embedding model (text-embedding-3-small)."""

    def __init__(self) -> None:
        self._api_key = os.getenv("OPENAI_API_KEY", "")

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        import httpx

        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY not set")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": EMBEDDING_MODEL_OPENAI,
                    "input": texts,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()

        return [item["embedding"] for item in data["data"]]
