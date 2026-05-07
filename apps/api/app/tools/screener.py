"""ScreenerTool — filter stocks by technical and fundamental criteria."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.base import BaseTool
from mr_market_shared.db.models import Technical, Fundamental, Stock

logger = logging.getLogger(__name__)

# Supported filter operators: {metric}_{op} where op is lt, gt, eq
_FILTER_COLUMNS: dict[str, tuple[str, Any]] = {
    # technicals
    "rsi_lt": ("technicals", Technical.rsi_14),
    "rsi_gt": ("technicals", Technical.rsi_14),
    "macd_gt": ("technicals", Technical.macd),
    "macd_lt": ("technicals", Technical.macd),
    # fundamentals
    "pe_lt": ("fundamentals", Fundamental.pe),
    "pe_gt": ("fundamentals", Fundamental.pe),
    "roe_gt": ("fundamentals", Fundamental.roe),
    "roe_lt": ("fundamentals", Fundamental.roe),
    "roce_gt": ("fundamentals", Fundamental.roce),
    "roce_lt": ("fundamentals", Fundamental.roce),
    "de_lt": ("fundamentals", Fundamental.debt_equity),
    "de_gt": ("fundamentals", Fundamental.debt_equity),
    "revenue_growth_gt": ("fundamentals", Fundamental.revenue_growth_pct),
    "profit_growth_gt": ("fundamentals", Fundamental.profit_growth_pct),
}


class ScreenerTool(BaseTool):
    """Screen stocks using a combination of technical and fundamental filters.

    Accepts a dict of filters like ``{"rsi_lt": 30, "roe_gt": 20}`` and
    returns matching tickers with their metric values.
    """

    name = "screen_stocks"
    description = (
        "Screen Indian stocks by technical and fundamental criteria. "
        "Supports filters like rsi_lt, roe_gt, pe_lt, de_lt, etc."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "filters": {
                "type": "object",
                "description": (
                    "Filter criteria as key-value pairs. Keys use the format "
                    "{metric}_{operator} — e.g. rsi_lt=30, roe_gt=20, pe_lt=15."
                ),
                "additionalProperties": {"type": "number"},
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results (default 10)",
                "default": 10,
            },
        },
        "required": ["filters"],
    }

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        filters: dict[str, float] = kwargs.get("filters", {})
        limit: int = kwargs.get("limit", 10)

        if not filters:
            return {"error": "No filters provided", "results": []}

        needs_technicals = any(
            _FILTER_COLUMNS.get(k, ("", None))[0] == "technicals" for k in filters
        )
        needs_fundamentals = any(
            _FILTER_COLUMNS.get(k, ("", None))[0] == "fundamentals" for k in filters
        )

        # Build query dynamically
        stmt = select(Stock.ticker, Stock.company_name, Stock.sector)

        if needs_technicals:
            stmt = stmt.join(Technical, Stock.ticker == Technical.ticker)
        if needs_fundamentals:
            stmt = stmt.join(Fundamental, Stock.ticker == Fundamental.ticker)

        conditions = []
        for filter_key, value in filters.items():
            meta = _FILTER_COLUMNS.get(filter_key)
            if meta is None:
                logger.warning("Unknown filter key: %s", filter_key)
                continue

            _table, column = meta
            if filter_key.endswith("_lt"):
                conditions.append(column < value)
            elif filter_key.endswith("_gt"):
                conditions.append(column > value)
            elif filter_key.endswith("_eq"):
                conditions.append(column == value)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        stmt = stmt.distinct().limit(limit)
        rows = (await self._db.execute(stmt)).all()

        results = [
            {
                "ticker": row.ticker,
                "company_name": row.company_name,
                "sector": row.sector,
            }
            for row in rows
        ]

        return {
            "filters_applied": filters,
            "count": len(results),
            "results": results,
            "source": "screener_db",
        }
