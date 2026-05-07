from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Deal(Base):
    """One row per NSE bulk- or block-deal trade.

    The natural key is (trade_date, symbol, client_name, side, kind, quantity,
    avg_price) — NSE can publish multiple deals for the same name on the same
    day, but exact-duplicate tuples are reruns we want to dedupe.
    """

    __tablename__ = "deals"
    __table_args__ = (
        UniqueConstraint(
            "trade_date",
            "symbol",
            "client_name",
            "side",
            "kind",
            "quantity",
            "avg_price",
            name="uq_deals_natural",
        ),
        Index("ix_deals_symbol_date", "symbol", "trade_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    security_name: Mapped[str | None] = mapped_column(Text)
    client_name: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    avg_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
