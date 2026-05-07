"""Nightly refresh task — orchestrates the complete data pipeline.

Runs at 04:00 IST daily. Must complete by 05:30 IST to have all data
ready for the 09:15 IST market open.

Pipeline stages:
1. Update stock universe (top 500 by market cap).
2. Scrape Screener.in fundamentals for all stocks.
3. Fetch OHLCV updates from yfinance.
4. Cross-validate fundamental data (Screener vs yfinance).
5. Compute technical indicators (RSI, MACD, BB, SMA, etc.).
6. Fetch NSE/BSE holdings and announcements.
7. Process news sentiment via FinBERT.
8. Invalidate Redis cache.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from typing import Any

import redis

from app.celery_app import celery

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from synchronous Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery.task(name="app.tasks.nightly_refresh.nightly_refresh_all", bind=True, max_retries=2)
def nightly_refresh_all(self: Any) -> dict[str, Any]:
    """Orchestrate the full nightly data refresh pipeline.

    This is the main Celery beat task. It runs all stages sequentially,
    logging progress and timing for each stage.
    """
    import time

    start = time.monotonic()
    report: dict[str, Any] = {"date": date.today().isoformat(), "stages": {}}

    try:
        # ----------------------------------------------------------
        # Stage 1: Update stock universe
        # ----------------------------------------------------------
        logger.info("nightly: [1/8] updating stock universe")
        stage_start = time.monotonic()
        tickers = _run_async(_update_stock_universe())
        report["stages"]["universe"] = {
            "count": len(tickers),
            "elapsed_s": round(time.monotonic() - stage_start, 1),
        }

        # ----------------------------------------------------------
        # Stage 2: Scrape fundamentals from Screener.in
        # ----------------------------------------------------------
        logger.info("nightly: [2/8] scraping Screener.in fundamentals for %d stocks", len(tickers))
        stage_start = time.monotonic()
        fundamentals = _run_async(_scrape_fundamentals(tickers))
        report["stages"]["fundamentals"] = {
            "count": len(fundamentals),
            "elapsed_s": round(time.monotonic() - stage_start, 1),
        }

        # ----------------------------------------------------------
        # Stage 3: Fetch OHLCV from yfinance
        # ----------------------------------------------------------
        logger.info("nightly: [3/8] fetching OHLCV data from yfinance")
        stage_start = time.monotonic()
        ohlcv_count = _run_async(_fetch_ohlcv(tickers))
        report["stages"]["ohlcv"] = {
            "count": ohlcv_count,
            "elapsed_s": round(time.monotonic() - stage_start, 1),
        }

        # ----------------------------------------------------------
        # Stage 4: Cross-validate (already done in stage 2)
        # ----------------------------------------------------------
        logger.info("nightly: [4/8] cross-validation complete (inline with screener)")
        report["stages"]["cross_validation"] = {"status": "done_inline"}

        # ----------------------------------------------------------
        # Stage 5: Compute technical indicators
        # ----------------------------------------------------------
        logger.info("nightly: [5/8] computing technical indicators")
        stage_start = time.monotonic()
        technicals = _run_async(_compute_technicals())
        report["stages"]["technicals"] = {
            "count": len(technicals),
            "elapsed_s": round(time.monotonic() - stage_start, 1),
        }

        # ----------------------------------------------------------
        # Stage 6: Fetch NSE/BSE holdings & announcements
        # ----------------------------------------------------------
        logger.info("nightly: [6/8] fetching NSE/BSE data")
        stage_start = time.monotonic()
        nse_bse = _run_async(_fetch_nse_bse_data())
        report["stages"]["nse_bse"] = {
            "count": nse_bse,
            "elapsed_s": round(time.monotonic() - stage_start, 1),
        }

        # ----------------------------------------------------------
        # Stage 7: Process news sentiment
        # ----------------------------------------------------------
        logger.info("nightly: [7/8] processing news sentiment")
        stage_start = time.monotonic()
        sentiment_count = _run_async(_process_news_sentiment())
        report["stages"]["sentiment"] = {
            "count": sentiment_count,
            "elapsed_s": round(time.monotonic() - stage_start, 1),
        }

        # ----------------------------------------------------------
        # Stage 8: Invalidate Redis cache
        # ----------------------------------------------------------
        logger.info("nightly: [8/8] invalidating Redis cache")
        stage_start = time.monotonic()
        _invalidate_cache()
        report["stages"]["cache_invalidation"] = {
            "status": "done",
            "elapsed_s": round(time.monotonic() - stage_start, 1),
        }

        report["status"] = "success"
        report["total_elapsed_s"] = round(time.monotonic() - start, 1)
        logger.info("nightly: pipeline completed in %.1fs", report["total_elapsed_s"])

    except Exception as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        report["total_elapsed_s"] = round(time.monotonic() - start, 1)
        logger.exception("nightly: pipeline failed after %.1fs", report["total_elapsed_s"])
        raise self.retry(exc=exc, countdown=300)

    return report


# ------------------------------------------------------------------
# Sub-task: FII/DII (scheduled separately at 18:00 IST)
# ------------------------------------------------------------------


@celery.task(name="app.tasks.nightly_refresh.fetch_fii_dii_data")
def fetch_fii_dii_data() -> dict[str, Any]:
    """Fetch daily FII/DII activity data from NSE."""
    from app.scrapers.nse_scraper import NSEScraper

    async def _run() -> list[dict[str, Any]]:
        scraper = NSEScraper()
        try:
            return await scraper.fetch_fii_dii()
        finally:
            await scraper.close()

    data = _run_async(_run())
    logger.info("nightly: fetched %d FII/DII records", len(data))
    return {"count": len(data), "date": date.today().isoformat()}


# ------------------------------------------------------------------
# Sub-task: Bulk deals (scheduled separately at 18:30 IST)
# ------------------------------------------------------------------


@celery.task(name="app.tasks.nightly_refresh.fetch_bulk_deals")
def fetch_bulk_deals() -> dict[str, Any]:
    """Fetch daily bulk/block deals from NSE."""
    from app.scrapers.nse_scraper import NSEScraper

    async def _run() -> list[dict[str, Any]]:
        scraper = NSEScraper()
        try:
            return await scraper.fetch_bulk_deals()
        finally:
            await scraper.close()

    data = _run_async(_run())
    logger.info("nightly: fetched %d bulk deal records", len(data))
    return {"count": len(data), "date": date.today().isoformat()}


# ======================================================================
# Internal pipeline stage implementations
# ======================================================================


async def _update_stock_universe() -> list[str]:
    """Refresh the stock universe — top 500 by market cap."""
    from mr_market_shared.db.models import Stock
    from mr_market_shared.db.session import get_session_manager
    from sqlalchemy import select

    manager = get_session_manager()
    async with manager.session() as session:
        stmt = (
            select(Stock.ticker)
            .where(Stock.is_nifty500.is_(True))
            .order_by(Stock.market_cap_cr.desc())
            .limit(500)
        )
        result = await session.execute(stmt)
        tickers = [row[0] for row in result.all()]

    logger.info("nightly: stock universe has %d tickers", len(tickers))
    return tickers


async def _scrape_fundamentals(tickers: list[str]) -> list[dict[str, Any]]:
    """Scrape Screener.in fundamentals with yfinance cross-validation."""
    from app.scrapers.screener_scraper import ScreenerScraper

    scraper = ScreenerScraper()
    try:
        results = await scraper.scrape_universe(tickers)
        await scraper.save(results)
        return results
    finally:
        await scraper.close()


async def _fetch_ohlcv(tickers: list[str]) -> int:
    """Fetch OHLCV data for all tickers from yfinance."""
    from app.scrapers.yfinance_scraper import YFinanceScraper

    scraper = YFinanceScraper()
    try:
        # Only fetch the last 5 days for nightly refresh (not full year)
        records = await scraper.fetch_ohlcv_batch(tickers, period_days=5)
        await scraper.save(records)
        return len(records)
    finally:
        await scraper.close()


async def _compute_technicals() -> list[dict[str, Any]]:
    """Compute technical indicators for all stocks."""
    from app.pipelines.technicals_compute import TechnicalsComputePipeline

    pipeline = TechnicalsComputePipeline()
    return await pipeline.run()


async def _fetch_nse_bse_data() -> int:
    """Fetch announcements and shareholding from NSE and BSE."""
    from app.scrapers.bse_scraper import BSEScraper
    from app.scrapers.nse_scraper import NSEScraper

    total = 0
    nse = NSEScraper()
    bse = BSEScraper()
    try:
        nse_data = await nse.scrape()
        total += len(nse_data)

        bse_data = await bse.scrape()
        total += len(bse_data)
    finally:
        await nse.close()
        await bse.close()

    return total


async def _process_news_sentiment() -> int:
    """Run FinBERT sentiment on all unprocessed news articles."""
    from mr_market_shared.db.models import News
    from mr_market_shared.db.session import get_session_manager
    from sqlalchemy import select, update

    from app.pipelines.sentiment import SentimentPipeline

    manager = get_session_manager()

    # Fetch unprocessed news
    async with manager.session() as session:
        stmt = select(News).where(News.sentiment_label.is_(None)).limit(500)
        result = await session.execute(stmt)
        articles = result.scalars().all()

    if not articles:
        return 0

    # Run sentiment pipeline
    pipeline = SentimentPipeline()
    headlines = [a.headline for a in articles if a.headline]
    results = pipeline.run(headlines)

    # Update news records with sentiment
    async with manager.session() as session:
        for article, sentiment in zip(articles, results, strict=False):
            stmt = (
                update(News)
                .where(News.id == article.id)
                .values(
                    sentiment_label=sentiment["sentiment_label"],
                    sentiment_score=sentiment["sentiment_score"],
                )
            )
            await session.execute(stmt)
        await session.commit()

    pipeline.unload_model()
    return len(results)


def _invalidate_cache() -> None:
    """Flush stale cache entries from Redis after nightly refresh."""
    client = redis.from_url(REDIS_URL)
    # Delete all cache keys with the mr_market prefix
    cursor = 0
    deleted = 0
    while True:
        cursor, keys = client.scan(cursor=cursor, match="mr_market:cache:*", count=100)
        if keys:
            client.delete(*keys)
            deleted += len(keys)
        if cursor == 0:
            break
    logger.info("nightly: invalidated %d cache keys", deleted)
    client.close()
