from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PriceDaily(Base):
    __tablename__ = "prices_daily"
    __table_args__ = (
        PrimaryKeyConstraint("ticker", "ts", "source", name="pk_prices_daily"),
    )

    ticker: Mapped[str] = mapped_column(
        String(32), ForeignKey("stocks.ticker", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    close: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    prev_close: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    delivery_qty: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
