"""RSS feed aggregator — Economic Times, Moneycontrol, Google News.

Aggregates financial news from multiple RSS feeds using feedparser.
Each feed is fetched and parsed independently, with results merged
and de-duplicated by URL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import feedparser  # type: ignore[import-untyped]

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedSource:
    """Definition of a single RSS feed source."""

    name: str
    url: str
    category: str = "general"


# Default feeds for Indian financial markets
DEFAULT_FEEDS: list[FeedSource] = [
    FeedSource(
        name="Economic Times - Markets",
        url="https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        category="market",
    ),
    FeedSource(
        name="Economic Times - Stocks",
        url="https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
        category="stocks",
    ),
    FeedSource(
        name="Moneycontrol - Markets",
        url="https://www.moneycontrol.com/rss/marketreports.xml",
        category="market",
    ),
    FeedSource(
        name="Moneycontrol - Business",
        url="https://www.moneycontrol.com/rss/business.xml",
        category="business",
    ),
    FeedSource(
        name="LiveMint - Markets",
        url="https://www.livemint.com/rss/markets",
        category="market",
    ),
]


class RSSFeedScraper(BaseScraper):
    """Aggregates news from multiple RSS feeds with de-duplication."""

    name = "rss_aggregator"
    source_url = "https://news.google.com"
    rate_limit = 2.0  # moderate; each feed is a single request

    def __init__(self, feeds: list[FeedSource] | None = None) -> None:
        super().__init__()
        self.feeds = feeds or DEFAULT_FEEDS
        self._seen_urls: set[str] = set()

    # ------------------------------------------------------------------
    # Google News ticker-specific feed
    # ------------------------------------------------------------------

    @staticmethod
    def google_news_url(ticker: str) -> str:
        """Build a Google News RSS URL filtered to a stock ticker.

        Searches for ``"<ticker> NSE stock"`` to get relevant results.
        """
        query = f"{ticker}+NSE+stock"
        return f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"

    # ------------------------------------------------------------------
    # Feed fetching and parsing
    # ------------------------------------------------------------------

    async def fetch_feed(self, source: FeedSource) -> list[dict[str, Any]]:
        """Fetch and parse a single RSS feed."""
        try:
            raw = await self.fetch(source.url)
            assert isinstance(raw, str)
            return self._parse_feed(raw, source)
        except Exception:
            logger.exception("rss: feed fetch failed for %s", source.name)
            return []

    def _parse_feed(self, xml: str, source: FeedSource) -> list[dict[str, Any]]:
        """Parse RSS XML into structured article records."""
        feed = feedparser.parse(xml)
        articles: list[dict[str, Any]] = []

        for entry in feed.entries:
            url = entry.get("link", "")

            # De-duplicate by URL
            if url in self._seen_urls:
                continue
            self._seen_urls.add(url)

            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])

            articles.append({
                "headline": entry.get("title", ""),
                "url": url,
                "summary": entry.get("summary", ""),
                "published_at": published.isoformat() if published else None,
                "source": source.name,
                "category": source.category,
            })

        return articles

    async def fetch_ticker_news(self, ticker: str) -> list[dict[str, Any]]:
        """Fetch Google News articles specific to a stock ticker."""
        url = self.google_news_url(ticker)
        source = FeedSource(name=f"google_news:{ticker}", url=url, category="ticker")
        return await self.fetch_feed(source)

    # ------------------------------------------------------------------
    # BaseScraper interface
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Fetch all configured RSS feeds and return merged results."""
        self._seen_urls.clear()
        all_articles: list[dict[str, Any]] = []

        for source in self.feeds:
            articles = await self.fetch_feed(source)
            all_articles.extend(articles)

        logger.info("rss: aggregated %d unique articles from %d feeds", len(all_articles), len(self.feeds))
        return all_articles

    async def save(self, data: list[dict[str, Any]]) -> int:
        """Persist aggregated news to the news table."""
        from mr_market_shared.db.models import News
        from mr_market_shared.db.session import get_session_manager

        manager = get_session_manager()
        saved = 0
        async with manager.session() as session:
            for article in data:
                news = News(
                    headline=article.get("headline"),
                    url=article.get("url"),
                    source=article.get("source", "rss"),
                    published_at=(
                        datetime.fromisoformat(article["published_at"])
                        if article.get("published_at")
                        else datetime.now()
                    ),
                )
                session.add(news)
                saved += 1
            await session.commit()
        logger.info("rss: saved %d articles", saved)
        return saved
