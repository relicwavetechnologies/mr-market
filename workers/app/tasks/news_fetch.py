"""Intraday news fetch task — every 15 minutes during market hours.

Fetches financial news from all RSS sources (Pulse, ET, Moneycontrol,
Google News), runs FinBERT sentiment analysis on new headlines, and
stores results in the ``news`` table with ticker linkage.

Schedule: every 15 min, Mon-Fri, 9:15 AM - 3:30 PM IST.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.celery_app import celery

logger = logging.getLogger(__name__)


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from synchronous Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery.task(name="app.tasks.news_fetch.fetch_latest_news", bind=True, max_retries=3)
def fetch_latest_news(self: Any) -> dict[str, Any]:
    """Fetch latest news from all sources, analyse sentiment, and store.

    Steps:
    1. Fetch from Zerodha Pulse (fastest, near real-time).
    2. Fetch from RSS aggregator (ET, Moneycontrol, Google News).
    3. De-duplicate against existing URLs in the news table.
    4. Run FinBERT sentiment on new headlines.
    5. Match tickers to headlines.
    6. Persist to database.
    """
    try:
        result = _run_async(_fetch_and_process())
        return result
    except Exception as exc:
        logger.exception("news_fetch: task failed")
        raise self.retry(exc=exc, countdown=60)


async def _fetch_and_process() -> dict[str, Any]:
    """Core async logic for news fetching and sentiment analysis."""
    from app.scrapers.pulse_scraper import PulseScraper
    from app.scrapers.rss_scraper import RSSFeedScraper

    # ------------------------------------------------------------------
    # Step 1 & 2: Fetch from all sources
    # ------------------------------------------------------------------
    pulse = PulseScraper()
    rss = RSSFeedScraper()

    try:
        pulse_articles = await pulse.scrape()
        rss_articles = await rss.scrape()
    finally:
        await pulse.close()
        await rss.close()

    all_articles = pulse_articles + rss_articles
    logger.info("news_fetch: fetched %d articles total", len(all_articles))

    if not all_articles:
        return {"fetched": 0, "new": 0, "sentiment_processed": 0}

    # ------------------------------------------------------------------
    # Step 3: De-duplicate against existing URLs
    # ------------------------------------------------------------------
    new_articles = await _deduplicate(all_articles)
    logger.info("news_fetch: %d new articles after de-duplication", len(new_articles))

    if not new_articles:
        return {"fetched": len(all_articles), "new": 0, "sentiment_processed": 0}

    # ------------------------------------------------------------------
    # Step 4: Run FinBERT sentiment
    # ------------------------------------------------------------------
    headlines = [a.get("headline", "") for a in new_articles if a.get("headline")]
    sentiment_results: list[dict[str, Any]] = []
    if headlines:
        from app.pipelines.sentiment import SentimentPipeline

        pipeline = SentimentPipeline()
        try:
            sentiment_results = pipeline.run(headlines)
        finally:
            pipeline.unload_model()

    # Map sentiment back to articles
    sentiment_map: dict[str, dict[str, Any]] = {}
    for result in sentiment_results:
        sentiment_map[result["headline"]] = result

    # ------------------------------------------------------------------
    # Step 5: Match tickers to headlines
    # ------------------------------------------------------------------
    known_tickers = await _get_known_tickers()
    for article in new_articles:
        headline = article.get("headline", "")
        # Simple ticker matching
        matched = _match_tickers(headline, known_tickers)
        article["ticker"] = matched[0] if matched else None

        # Attach sentiment
        sentiment = sentiment_map.get(headline)
        if sentiment:
            article["sentiment_label"] = sentiment["sentiment_label"]
            article["sentiment_score"] = sentiment["sentiment_score"]

    # ------------------------------------------------------------------
    # Step 6: Persist to database
    # ------------------------------------------------------------------
    saved = await _save_articles(new_articles)

    return {
        "fetched": len(all_articles),
        "new": len(new_articles),
        "sentiment_processed": len(sentiment_results),
        "saved": saved,
    }


async def _deduplicate(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove articles whose URL already exists in the database."""
    from mr_market_shared.db.models import News
    from mr_market_shared.db.session import get_session_manager
    from sqlalchemy import select

    urls = [a.get("url") for a in articles if a.get("url")]
    if not urls:
        return articles

    manager = get_session_manager()
    async with manager.session() as session:
        stmt = select(News.url).where(News.url.in_(urls))
        result = await session.execute(stmt)
        existing_urls = {row[0] for row in result.all()}

    return [a for a in articles if a.get("url") not in existing_urls]


async def _get_known_tickers() -> set[str]:
    """Load all known ticker symbols from the database."""
    from mr_market_shared.db.models import Stock
    from mr_market_shared.db.session import get_session_manager
    from sqlalchemy import select

    manager = get_session_manager()
    async with manager.session() as session:
        stmt = select(Stock.ticker)
        result = await session.execute(stmt)
        return {row[0] for row in result.all()}


def _match_tickers(headline: str, known_tickers: set[str]) -> list[str]:
    """Match stock tickers mentioned in a headline.

    Uses word-boundary matching against the known ticker set.
    This is a simple heuristic; production should use NER.
    """
    words = set(headline.upper().replace(",", " ").replace(".", " ").split())
    # Filter out common English words that happen to be short tickers
    noise = {"A", "I", "IT", "IN", "ON", "AT", "TO", "OR", "IF", "IS", "BE", "BY", "OF"}
    return [t for t in known_tickers if t in words and t not in noise]


async def _save_articles(articles: list[dict[str, Any]]) -> int:
    """Persist new articles to the news table."""
    from mr_market_shared.db.models import News
    from mr_market_shared.db.session import get_session_manager

    manager = get_session_manager()
    saved = 0
    async with manager.session() as session:
        for article in articles:
            published_at = None
            if article.get("published_at"):
                try:
                    published_at = datetime.fromisoformat(article["published_at"])
                except (ValueError, TypeError):
                    published_at = datetime.now()

            news = News(
                ticker=article.get("ticker"),
                headline=article.get("headline"),
                url=article.get("url"),
                published_at=published_at or datetime.now(),
                source=article.get("source", "unknown"),
                sentiment_label=article.get("sentiment_label"),
                sentiment_score=(
                    Decimal(str(article["sentiment_score"]))
                    if article.get("sentiment_score") is not None
                    else None
                ),
            )
            session.add(news)
            saved += 1
        await session.commit()

    logger.info("news_fetch: saved %d articles to database", saved)
    return saved
