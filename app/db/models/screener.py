"""Stored screener — a saved expression in the screener DSL (P3-A3).

Six "seed packs" are inserted by the Alembic migration on first apply
(`oversold_quality`, `value_rebound`, `momentum_breakout`,
`high_pledge_avoid`, `fii_buying`, `promoter_increasing`). User-saved
screeners can be added later in Phase 3+; the `is_seed` column flags
which rows came from the migration vs the user.

The expression is a plain text column — `app.analytics.screener.compile_expr`
parses + validates it at run time, so we don't denormalise the AST.
Validation on INSERT happens at the API layer (the only writer).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Screener(Base):
    __tablename__ = "screeners"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    expr: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_seed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
