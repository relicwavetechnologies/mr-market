"""Stock master table model."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from mr_market_shared.db.base import Base


class Stock(Base):
    """Represents a listed stock in the master universe."""

    __tablename__ = "stocks"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    company_name: Mapped[str | None] = mapped_column(String(200))
    sector: Mapped[str | None] = mapped_column(String(100))
    industry: Mapped[str | None] = mapped_column(String(100))
    cap: Mapped[str | None] = mapped_column(String(20))
    nse_listed: Mapped[bool] = mapped_column(default=True)
    bse_code: Mapped[str | None] = mapped_column(String(20))
    market_cap_cr: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    is_nifty50: Mapped[bool] = mapped_column(default=False)
    is_nifty500: Mapped[bool] = mapped_column(default=False)
    is_fno: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
