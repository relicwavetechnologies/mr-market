from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class News(Base):
    __tablename__ = "news"
    __table_args__ = (
        Index("ix_news_published", "published_at"),
        Index("ix_news_tickers", "tickers", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    tickers: Mapped[list[str] | None] = mapped_column(ARRAY(String(32)))
    sentiment: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    sentiment_label: Mapped[str | None] = mapped_column(String(16))
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
