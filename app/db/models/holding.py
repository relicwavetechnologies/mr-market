from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, PrimaryKeyConstraint, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Holding(Base):
    """Quarterly NSE shareholding pattern, one row per ticker × quarter-end."""

    __tablename__ = "holdings"
    __table_args__ = (PrimaryKeyConstraint("ticker", "quarter_end", name="pk_holdings"),)

    ticker: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("stocks.ticker", ondelete="CASCADE"),
        nullable=False,
    )
    quarter_end: Mapped[date] = mapped_column(Date, nullable=False)

    promoter_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    public_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    employee_trust_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    xbrl_url: Mapped[str | None] = mapped_column(Text)
    submission_date: Mapped[date | None] = mapped_column(Date)
    broadcast_date: Mapped[date | None] = mapped_column(Date)

    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
