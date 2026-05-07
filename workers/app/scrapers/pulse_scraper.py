"""Zerodha Pulse scraper — low-latency financial news via RSS.

Zerodha Pulse provides near-real-time financial news aggregation with
sub-minute latency. Free and unlimited — no rate-limiting needed.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import feedparser  # type: ignore[import-untyped]

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

PULSE_RSS_URL = "https://pulse.zerodha.com/feeds"


class PulseScraper(BaseScraper):
    """Scrapes Zerodha Pulse RSS feed for near-real-time financial news."""

    name = "pulse"
    source_url = PULSE_RSS_URL
    rate_limit = 10.0  # effectively unlimited; keep reasonable

    # ------------------------------------------------------------------
    # RSS feed parsing
    # ------------------------------------------------------------------

    async def fetch_news(self) -> list[dict[str, Any]]:
        """Fetch and parse the latest news from Zerodha Pulse RSS feed."""
        try:
            raw = await self.fetch(self.source_url)
            assert isinstance(raw, str)
            return self._parse_feed(raw)
        except Exception:
            logger.exception("pulse: feed fetch failed")
            return []

    def _parse_feed(self, xml: str) -> list[dict[str, Any]]:
        """Parse RSS XML into structured news records."""
        feed = feedparser.parse(xml)
        articles: list[dict[str, Any]] = []

        for entry in feed.entries:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])

            # Extract source from the feed entry
            source_name = "pulse"
            if hasattr(entry, "source") and hasattr(entry.source, "title"):
                source_name = f"pulse:{entry.source.title}"

            articles.append({
                "headline": entry.get("title", ""),
                "url": entry.get("link", ""),
                "summary": entry.get("summary", ""),
                "published_at": published.isoformat() if published else None,
                "source": source_name,
                "tags": [tag.term for tag in getattr(entry, "tags", [])],
            })

        logger.info("pulse: parsed %d articles from feed", len(articles))
        return articles

    # ------------------------------------------------------------------
    # Ticker extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_tickers(headline: str, known_tickers: set[str]) -> list[str]:
        """Attempt to match stock tickers mentioned in a headline.

        Uses a simple word-boundary match against the known ticker
        universe. For production, this should be replaced with NER.
        """
        words = set(headline.upper().split())
        return [t for t in known_tickers if t in words]

    # ------------------------------------------------------------------
    # BaseScraper interface
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Fetch latest Pulse news."""
        return await self.fetch_news()

    async def save(self, data: list[dict[str, Any]]) -> int:
        """Persist Pulse news to the news table."""
        from mr_market_shared.db.models import News
        from mr_market_shared.db.session import get_session_manager

        manager = get_session_manager()
        saved = 0
        async with manager.session() as session:
            for article in data:
                news = News(
                    headline=article.get("headline"),
                    url=article.get("url"),
                    source=article.get("source", "pulse"),
                    published_at=(
                        datetime.fromisoformat(article["published_at"])
                        if article.get("published_at")
                        else datetime.now()
                    ),
                )
                session.add(news)
                saved += 1
            await session.commit()
        logger.info("pulse: saved %d articles", saved)
        return saved
