"""RiskProfileTool — look up a user's risk profile and trading preferences."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.base import BaseTool
from mr_market_shared.db.models import User

logger = logging.getLogger(__name__)


class RiskProfileTool(BaseTool):
    """Retrieve a user's risk profile and onboarding answers.

    Used by the orchestrator to tailor advice (e.g. gating F&O for
    conservative users).
    """

    name = "check_risk_profile"
    description = (
        "Get the risk profile and trading preferences for a user. "
        "Returns conservative / moderate / aggressive classification."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "UUID of the user",
            },
        },
        "required": ["user_id"],
    }

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        user_id_str: str = kwargs["user_id"]

        try:
            user_uuid = UUID(user_id_str)
        except ValueError:
            return {"error": f"Invalid user_id format: {user_id_str}"}

        stmt = select(User).where(User.id == user_uuid)
        user = (await self._db.execute(stmt)).scalar_one_or_none()

        if user is None:
            return {"error": f"User not found: {user_id_str}"}

        onboarding = user.onboarding_answers or {}

        return {
            "user_id": str(user.id),
            "risk_profile": user.risk_profile or "moderate",
            "experience_level": onboarding.get("experience_level", "unknown"),
            "investment_horizon": onboarding.get("investment_horizon", "unknown"),
            "preferred_segments": onboarding.get("preferred_segments", ["equity"]),
            "max_loss_tolerance_pct": onboarding.get("max_loss_tolerance_pct", 10),
            "source": "database",
        }
