"""FundamentalsTool — retrieve fundamental analysis data for a ticker."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.base import BaseTool
from mr_market_shared.db.models import Fundamental

logger = logging.getLogger(__name__)


class FundamentalsTool(BaseTool):
    """Fetch the latest fundamental data (P/E, ROE, ROCE, etc.) for a stock.

    Reads from the ``fundamentals`` table which is populated by the Screener
    scraper pipeline.
    """

    name = "get_fundamentals"
    description = (
        "Get fundamental analysis data for an Indian stock — P/E, ROE, ROCE, "
        "D/E ratio, revenue growth, EPS, book value, and more."
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
            select(Fundamental)
            .where(Fundamental.ticker == ticker)
            .order_by(Fundamental.scraped_date.desc())
            .limit(1)
        )
        row = (await self._db.execute(stmt)).scalar_one_or_none()

        if row is None:
            return {"error": f"No fundamental data for {ticker}", "ticker": ticker}

        return {
            "ticker": row.ticker,
            "scraped_date": row.scraped_date.isoformat(),
            "market_cap": float(row.market_cap) if row.market_cap else None,
            "pe": float(row.pe) if row.pe else None,
            "pe_industry": float(row.pe_industry) if row.pe_industry else None,
            "pb": float(row.pb) if row.pb else None,
            "roe": float(row.roe) if row.roe else None,
            "roce": float(row.roce) if row.roce else None,
            "debt_equity": float(row.debt_equity) if row.debt_equity else None,
            "revenue_growth_pct": float(row.revenue_growth_pct) if row.revenue_growth_pct else None,
            "profit_growth_pct": float(row.profit_growth_pct) if row.profit_growth_pct else None,
            "dividend_yield_pct": float(row.dividend_yield_pct) if row.dividend_yield_pct else None,
            "eps": float(row.eps) if row.eps else None,
            "book_value": float(row.book_value) if row.book_value else None,
            "confidence": row.confidence,
            "source": "screener",
        }
