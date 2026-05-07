"""Live price streaming task — periodic polling via yfinance for MVP.

Production target: WebSocket connection to broker API (Zerodha Kite,
Angel One) for real-time tick data. MVP implementation polls yfinance
every 5 seconds during market hours.

Schedule: triggered manually or by a separate beat entry during
market hours (9:15 AM - 3:30 PM IST, Mon-Fri).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, time, timezone, timedelta
from typing import Any

import redis

from app.celery_app import celery

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# IST timezone offset
IST = timezone(timedelta(hours=5, minutes=30))

# Market hours
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)

# Polling interval in seconds (MVP)
POLL_INTERVAL_SECONDS = 5

# Redis channel for price updates
PRICE_CHANNEL = "mr_market:prices:live"

# Maximum tickers to poll per cycle (MVP constraint)
MAX_TICKERS_PER_CYCLE = 50


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from synchronous Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery.task(name="app.tasks.price_streaming.stream_prices", bind=True)
def stream_prices(
    self: Any,
    tickers: list[str] | None = None,
    duration_minutes: int = 15,
) -> dict[str, Any]:
    """Poll live prices via yfinance and publish to Redis.

    This is an MVP implementation. In production, this will be replaced
    by a WebSocket connection to a broker API (Zerodha Kite / Angel One).

    Parameters
    ----------
    tickers:
        List of tickers to poll. If ``None``, polls Nifty 50 constituents.
    duration_minutes:
        How long to keep polling (default: 15 min, one beat cycle).
    """
    if not _is_market_hours():
        logger.info("price_streaming: market is closed, skipping")
        return {"status": "market_closed"}

    try:
        result = _run_async(_poll_prices(tickers, duration_minutes))
        return result
    except Exception as exc:
        logger.exception("price_streaming: task failed")
        return {"status": "error", "error": str(exc)}


async def _poll_prices(
    tickers: list[str] | None,
    duration_minutes: int,
) -> dict[str, Any]:
    """Core polling loop — fetches quotes and publishes to Redis."""
    import json

    from app.scrapers.yfinance_scraper import YFinanceScraper

    # Load tickers if not provided
    if not tickers:
        tickers = await _get_nifty50_tickers()

    # Limit for MVP
    tickers = tickers[:MAX_TICKERS_PER_CYCLE]

    scraper = YFinanceScraper()
    redis_client = redis.from_url(REDIS_URL)

    total_updates = 0
    cycles = 0
    start = asyncio.get_event_loop().time()
    deadline = start + (duration_minutes * 60)

    try:
        while asyncio.get_event_loop().time() < deadline:
            if not _is_market_hours():
                logger.info("price_streaming: market closed, stopping")
                break

            cycle_updates = 0
            for ticker in tickers:
                quote = await scraper.fetch_quote(ticker)
                if quote and quote.get("price"):
                    # Publish to Redis pub/sub
                    redis_client.publish(
                        PRICE_CHANNEL,
                        json.dumps(quote, default=str),
                    )
                    # Also cache the latest price
                    redis_client.set(
                        f"mr_market:price:{ticker}",
                        json.dumps(quote, default=str),
                        ex=30,  # expire in 30 seconds
                    )
                    cycle_updates += 1

            total_updates += cycle_updates
            cycles += 1
            logger.debug(
                "price_streaming: cycle %d — %d updates",
                cycles,
                cycle_updates,
            )

            # Wait before next poll
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    finally:
        await scraper.close()
        redis_client.close()

    return {
        "status": "completed",
        "tickers_polled": len(tickers),
        "total_updates": total_updates,
        "cycles": cycles,
        "duration_minutes": duration_minutes,
    }


async def _get_nifty50_tickers() -> list[str]:
    """Load Nifty 50 tickers from the database."""
    from mr_market_shared.db.models import Stock
    from mr_market_shared.db.session import get_session_manager
    from sqlalchemy import select

    manager = get_session_manager()
    async with manager.session() as session:
        stmt = select(Stock.ticker).where(Stock.is_nifty50.is_(True))
        result = await session.execute(stmt)
        return [row[0] for row in result.all()]


def _is_market_hours() -> bool:
    """Check if current IST time is within market hours (Mon-Fri, 9:15-15:30)."""
    now_ist = datetime.now(IST)
    # Monday = 0, Sunday = 6
    if now_ist.weekday() >= 5:
        return False
    current_time = now_ist.time()
    return MARKET_OPEN <= current_time <= MARKET_CLOSE
