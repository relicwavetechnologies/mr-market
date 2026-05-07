from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatAudit(Base):
    __tablename__ = "chat_audit"
    __table_args__ = (Index("ix_chat_audit_user_ts", "user_id", "ts"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(64))
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(32))
    retrieved: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(64))
    output: Mapped[str | None] = mapped_column(Text)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    flagged: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_inr: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
