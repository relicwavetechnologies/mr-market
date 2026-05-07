"""NewsTool — fetch recent sentiment-tagged news for a ticker."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.base import BaseTool
from mr_market_shared.db.models import News

logger = logging.getLogger(__name__)


class NewsTool(BaseTool):
    """Retrieve the latest news articles with sentiment scores for a stock."""

    name = "fetch_news"
    description = (
        "Fetch recent news articles for an Indian stock, each tagged with "
        "sentiment (positive/negative/neutral) and impact level."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "NSE ticker symbol",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of articles to return (default 5)",
                "default": 5,
            },
        },
        "required": ["ticker"],
    }

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        ticker: str = kwargs["ticker"].upper().strip()
        limit: int = kwargs.get("limit", 5)

        stmt = (
            select(News)
            .where(News.ticker == ticker)
            .order_by(News.published_at.desc())
            .limit(limit)
        )
        rows = (await self._db.execute(stmt)).scalars().all()

        if not rows:
            return {
                "ticker": ticker,
                "articles": [],
                "overall_sentiment": "neutral",
                "source": "database",
            }

        articles = [
            {
                "headline": row.headline,
                "url": row.url,
                "published_at": row.published_at.isoformat() if row.published_at else None,
                "source": row.source,
                "sentiment_label": row.sentiment_label,
                "sentiment_score": float(row.sentiment_score) if row.sentiment_score else None,
                "impact": row.impact,
            }
            for row in rows
        ]

        overall = self._compute_overall_sentiment(articles)

        return {
            "ticker": ticker,
            "articles": articles,
            "overall_sentiment": overall,
            "source": "database",
        }

    @staticmethod
    def _compute_overall_sentiment(articles: list[dict[str, Any]]) -> str:
        """Aggregate individual sentiment scores into an overall label."""
        scores = [
            a["sentiment_score"]
            for a in articles
            if a["sentiment_score"] is not None
        ]
        if not scores:
            return "neutral"

        avg = sum(scores) / len(scores)
        if avg > 0.15:
            return "positive"
        if avg < -0.15:
            return "negative"
        return "neutral"
