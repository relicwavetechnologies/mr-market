"""Shareholding pattern data model."""

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from mr_market_shared.db.base import Base


class Shareholding(Base):
    """Stores quarterly shareholding pattern for a stock."""

    __tablename__ = "shareholding"

    ticker: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("stocks.ticker"),
        primary_key=True,
    )
    quarter: Mapped[str] = mapped_column(String(10), primary_key=True)  # e.g. 'Q1-2026'
    promoter_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    promoter_pledge_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    fii_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    dii_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    retail_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    fii_change: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))  # vs last quarter
