"""HoldingTool — retrieve the latest shareholding pattern for a ticker."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.base import BaseTool
from mr_market_shared.db.models import Shareholding

logger = logging.getLogger(__name__)


class HoldingTool(BaseTool):
    """Fetch the latest quarterly shareholding pattern for a stock."""

    name = "get_shareholding"
    description = (
        "Get the latest shareholding pattern — promoter, FII, DII, retail "
        "percentages and promoter pledge status for an Indian stock."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "NSE ticker symbol",
            },
        },
        "required": ["ticker"],
    }

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        ticker: str = kwargs["ticker"].upper().strip()

        stmt = (
            select(Shareholding)
            .where(Shareholding.ticker == ticker)
            .order_by(Shareholding.quarter.desc())
            .limit(1)
        )
        row = (await self._db.execute(stmt)).scalar_one_or_none()

        if row is None:
            return {"error": f"No shareholding data for {ticker}", "ticker": ticker}

        return {
            "ticker": row.ticker,
            "quarter": row.quarter,
            "promoter_pct": float(row.promoter_pct) if row.promoter_pct else None,
            "promoter_pledge_pct": float(row.promoter_pledge_pct) if row.promoter_pledge_pct else None,
            "fii_pct": float(row.fii_pct) if row.fii_pct else None,
            "dii_pct": float(row.dii_pct) if row.dii_pct else None,
            "retail_pct": float(row.retail_pct) if row.retail_pct else None,
            "fii_change": float(row.fii_change) if row.fii_change else None,
            "source": "database",
        }
