"""Tool registry and exports for all agent tools."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis import RedisCache
from app.services.intent_router import Intent
from app.tools.base import BaseTool
from app.tools.concall_rag import ConcallRagTool
from app.tools.fundamentals import FundamentalsTool
from app.tools.holding import HoldingTool
from app.tools.news import NewsTool
from app.tools.price import PriceTool
from app.tools.risk_profile import RiskProfileTool
from app.tools.screener import ScreenerTool
from app.tools.technicals import TechnicalsTool

logger = logging.getLogger(__name__)

__all__ = [
    "BaseTool",
    "ConcallRagTool",
    "FundamentalsTool",
    "HoldingTool",
    "NewsTool",
    "PriceTool",
    "RiskProfileTool",
    "ScreenerTool",
    "TechnicalsTool",
    "ToolRegistry",
]

# Maps intents to the subset of tools the LLM should have access to.
_INTENT_TOOL_MAP: dict[Intent, list[str]] = {
    Intent.STOCK_PRICE: ["get_live_price"],
    Intent.STOCK_ANALYSIS: [
        "get_live_price",
        "calc_technicals",
        "get_fundamentals",
        "fetch_news",
        "get_shareholding",
        "search_concall",
    ],
    Intent.WHY_MOVING: [
        "get_live_price",
        "fetch_news",
        "calc_technicals",
    ],
    Intent.SCREENER: ["screen_stocks"],
    Intent.PORTFOLIO: [
        "get_live_price",
        "get_fundamentals",
        "check_risk_profile",
    ],
    Intent.GENERAL: [],
}


class ToolRegistry:
    """Central registry that holds all tool instances and dispatches calls."""

    def __init__(self, db: AsyncSession, redis: RedisCache) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._register_defaults(db, redis)

    def register(self, tool: BaseTool) -> None:
        """Add a tool to the registry."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Retrieve a tool by name."""
        return self._tools.get(name)

    async def execute(self, name: str, **kwargs: Any) -> dict[str, Any]:
        """Look up a tool by name and execute it."""
        tool = self._tools.get(name)
        if tool is None:
            logger.error("Tool not found: %s", name)
            return {"error": f"Unknown tool: {name}"}
        return await tool.execute(**kwargs)

    def get_schemas_for_intent(self, intent: Intent) -> list[dict[str, Any]]:
        """Return function-calling schemas for the tools relevant to *intent*."""
        tool_names = _INTENT_TOOL_MAP.get(intent, [])
        schemas: list[dict[str, Any]] = []
        for name in tool_names:
            tool = self._tools.get(name)
            if tool:
                schemas.append(tool.to_function_schema())
        return schemas

    def all_schemas(self) -> list[dict[str, Any]]:
        """Return schemas for every registered tool."""
        return [t.to_function_schema() for t in self._tools.values()]

    # ------------------------------------------------------------------
    # Default registration
    # ------------------------------------------------------------------

    def _register_defaults(self, db: AsyncSession, redis: RedisCache) -> None:
        """Instantiate and register all built-in tools."""
        self.register(PriceTool(db=db, redis=redis))
        self.register(TechnicalsTool(db=db))
        self.register(FundamentalsTool(db=db))
        self.register(NewsTool(db=db))
        self.register(HoldingTool(db=db))
        self.register(ScreenerTool(db=db))
        self.register(RiskProfileTool(db=db))
        self.register(ConcallRagTool())
