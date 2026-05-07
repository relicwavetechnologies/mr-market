"""Technical indicator data model."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from mr_market_shared.db.base import Base


class Technical(Base):
    """Stores computed technical indicators for a stock on a given date."""

    __tablename__ = "technicals"

    ticker: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("stocks.ticker"),
        primary_key=True,
    )
    computed_date: Mapped[date] = mapped_column(Date, primary_key=True)
    rsi_14: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    macd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    macd_signal: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    bb_upper: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    bb_lower: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sma_20: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sma_50: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sma_200: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    ema_20: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    pivot: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    support_1: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    support_2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    resistance_1: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    resistance_2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    atr: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    trend: Mapped[str | None] = mapped_column(String(20))  # bullish / bearish / sideways
