from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Numeric,
    PrimaryKeyConstraint,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Technicals(Base):
    """Per-ticker, per-trade-date technical indicator snapshot.

    Computed nightly off `prices_daily`. One row per (ticker, ts).
    All columns are nullable because the early bars in a series don't have
    enough history for some indicators (e.g. SMA-200 needs >=200 bars).
    """

    __tablename__ = "technicals"
    __table_args__ = (PrimaryKeyConstraint("ticker", "ts", name="pk_technicals"),)

    ticker: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("stocks.ticker", ondelete="CASCADE"),
        nullable=False,
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Denormalised close (saves a join in the common API path)
    close: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    # Momentum
    rsi_14: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    # MACD (12, 26, 9)
    macd: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    macd_signal: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    macd_hist: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))

    # Bollinger Bands (20, 2)
    bb_upper: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    bb_middle: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    bb_lower: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    # SMAs
    sma_20: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    sma_50: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    sma_200: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    # EMAs
    ema_12: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    ema_26: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    # Volatility
    atr_14: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    # Volume context
    vol_avg_20: Mapped[int | None] = mapped_column(BigInteger)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
