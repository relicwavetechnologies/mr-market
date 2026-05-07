"""News and sentiment data model."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from mr_market_shared.db.base import Base


class News(Base):
    """Stores news articles and their sentiment analysis for stocks."""

    __tablename__ = "news"
    __table_args__ = (
        Index("idx_news_ticker_time", "ticker", "published_at", postgresql_using="btree"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str | None] = mapped_column(String(20))
    headline: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text, unique=True)
    published_at: Mapped[datetime | None] = mapped_column()
    source: Mapped[str | None] = mapped_column(String(100))
    sentiment_label: Mapped[str | None] = mapped_column(String(20))  # positive / negative / neutral
    sentiment_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))  # -1.0 to 1.0
    impact: Mapped[str | None] = mapped_column(String(20))  # high / medium / low
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
