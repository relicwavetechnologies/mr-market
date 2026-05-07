"""Fundamental analysis data model."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from mr_market_shared.db.base import Base


class Fundamental(Base):
    """Stores scraped fundamental data for a stock on a given date."""

    __tablename__ = "fundamentals"

    ticker: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("stocks.ticker"),
        primary_key=True,
    )
    scraped_date: Mapped[date] = mapped_column(Date, primary_key=True)
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    pe: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    pe_industry: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    pb: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    roe: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    roce: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    debt_equity: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    revenue_growth_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    profit_growth_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    dividend_yield_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    eps: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    book_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    confidence: Mapped[str | None] = mapped_column(String(20))  # HIGH / MEDIUM / LOW
