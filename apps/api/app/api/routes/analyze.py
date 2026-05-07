"""Stock analysis endpoint — aggregates technicals, fundamentals, news, and holdings."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSessionDep, RedisDep, SettingsDep
from app.tools.fundamentals import FundamentalsTool
from app.tools.holding import HoldingTool
from app.tools.news import NewsTool
from app.tools.price import PriceTool
from app.tools.technicals import TechnicalsTool

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class AnalysisResponse(BaseModel):
    """Complete analysis output for a single ticker."""

    ticker: str
    price: dict[str, Any] = Field(default_factory=dict)
    technicals: dict[str, Any] = Field(default_factory=dict)
    fundamentals: dict[str, Any] = Field(default_factory=dict)
    news: list[dict[str, Any]] = Field(default_factory=list)
    shareholding: dict[str, Any] = Field(default_factory=dict)
    generated_at: str = ""


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("/{ticker}", response_model=AnalysisResponse)
async def analyze_ticker(
    ticker: str,
    db: DBSessionDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> AnalysisResponse:
    """Return a full analysis report for the requested ticker.

    Fetches data from all available tools concurrently using
    ``asyncio.gather`` and merges results into a single response.
    """
    ticker_upper = ticker.upper().strip()

    price_tool = PriceTool(db=db, redis=redis)
    technicals_tool = TechnicalsTool(db=db)
    fundamentals_tool = FundamentalsTool(db=db)
    news_tool = NewsTool(db=db)
    holding_tool = HoldingTool(db=db)

    price_data, tech_data, fund_data, news_data, hold_data = await asyncio.gather(
        price_tool.execute(ticker=ticker_upper),
        technicals_tool.execute(ticker=ticker_upper),
        fundamentals_tool.execute(ticker=ticker_upper),
        news_tool.execute(ticker=ticker_upper, limit=5),
        holding_tool.execute(ticker=ticker_upper),
        return_exceptions=True,
    )

    def _safe(result: Any) -> Any:
        """Return the result if it succeeded, otherwise an error dict."""
        if isinstance(result, BaseException):
            logger.warning("Tool failed during analysis: %s", result)
            return {"error": str(result)}
        return result

    from datetime import datetime, timezone

    return AnalysisResponse(
        ticker=ticker_upper,
        price=_safe(price_data),
        technicals=_safe(tech_data),
        fundamentals=_safe(fund_data),
        news=_safe(news_data) if not isinstance(news_data, BaseException) else [],
        shareholding=_safe(hold_data),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
