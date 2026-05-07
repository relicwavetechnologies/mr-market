"""OHLCV price data model."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from mr_market_shared.db.base import Base


class Price(Base):
    """Stores OHLCV price data for a stock at a given timestamp."""

    __tablename__ = "prices"

    ticker: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("stocks.ticker"),
        primary_key=True,
    )
    timestamp: Mapped[datetime] = mapped_column(primary_key=True)
    open: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    high: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    low: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    close: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str | None] = mapped_column(String(50))
