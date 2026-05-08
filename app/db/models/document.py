from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Document(Base):
    """A source document (annual report, concall transcript, XBRL filing).

    One row per (ticker, kind, fy). The text is chunked and stored separately
    in `document_chunks`.
    """

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("ticker", "kind", "fy", name="uq_documents_natural"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(
        String(32), ForeignKey("stocks.ticker", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    fy: Mapped[str | None] = mapped_column(String(16))
    source_url: Mapped[str | None] = mapped_column(Text)
    source_path: Mapped[str | None] = mapped_column(Text)
    n_pages: Mapped[int | None] = mapped_column(Integer)
    n_chunks: Mapped[int | None] = mapped_column(Integer)
    embedding_model: Mapped[str | None] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DocumentChunk(Base):
    """One chunk of a `Document` with its OpenAI embedding stored as JSONB.

    JSONB is a deliberate choice over pgvector — for our demo corpus
    (≤ 10 docs × ~80 chunks = 800 vectors total) numpy cosine over a single
    SELECT is faster than maintaining a pgvector extension build for
    Postgres 16, and keeps the dep surface flat. Easy to swap to pgvector
    later without changing the API contract.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_idx", name="uq_document_chunks_natural"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSONB)
    n_tokens: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
