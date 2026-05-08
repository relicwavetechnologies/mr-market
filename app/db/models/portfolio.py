"""User-owned portfolios + holdings (P3-A4).

Two tables, one per concept:
- `portfolios`     — header row per import (one user can have many).
- `holdings_user`  — per-position rows; FK CASCADE on portfolio delete.

The `Holding` model in `app/db/models/holding.py` already exists for NSE
shareholding-pattern data — DO NOT confuse the two. `holdings_user` is a
DIFFERENT table; the `_user` suffix avoids collision and signals scope.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(128), nullable=False, server_default="My Portfolio"
    )
    source: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # "csv" | "cdsl_paste" | "api" — informational
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class HoldingUser(Base):
    """One row per (portfolio, ticker). De-duplicated on import — the parser
    collapses repeated lines into a single row with summed quantity and a
    weighted-average cost."""

    __tablename__ = "holdings_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("stocks.ticker", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
