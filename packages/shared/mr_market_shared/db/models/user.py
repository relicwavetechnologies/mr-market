"""User model with risk profile and onboarding data."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mr_market_shared.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    """Application user with risk profile and onboarding answers."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    risk_profile: Mapped[str | None] = mapped_column(
        String(20),
    )  # conservative / moderate / aggressive
    onboarding_answers: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(default=True)
    last_login_at: Mapped[datetime | None] = mapped_column()
