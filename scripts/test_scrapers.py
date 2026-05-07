#!/usr/bin/env python3
"""CLI to test individual scrapers for a given ticker.

Usage:
    python scripts/test_scrapers.py --ticker RELIANCE
    python scripts/test_scrapers.py --ticker TCS --scraper fundamentals
    python scripts/test_scrapers.py --ticker INFY --scraper news --verbose

Available scrapers: fundamentals, technicals, news, holdings, price
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def test_fundamentals(ticker: str, verbose: bool) -> dict:
    """Test the fundamentals scraper."""
    from workers.app.scrapers.fundamentals import FundamentalsScraper

    scraper = FundamentalsScraper()
    print(f"Fetching fundamentals for {ticker}...")
    result = await scraper.scrape(ticker)
    return result


async def test_technicals(ticker: str, verbose: bool) -> dict:
    """Test the technicals scraper."""
    from workers.app.scrapers.technicals import TechnicalsScraper

    scraper = TechnicalsScraper()
    print(f"Fetching technicals for {ticker}...")
    result = await scraper.scrape(ticker)
    return result


async def test_news(ticker: str, verbose: bool) -> dict:
    """Test the news scraper."""
    from workers.app.scrapers.news import NewsScraper

    scraper = NewsScraper()
    print(f"Fetching news for {ticker}...")
    result = await scraper.scrape(ticker)
    return result


async def test_holdings(ticker: str, verbose: bool) -> dict:
    """Test the holdings scraper."""
    from workers.app.scrapers.holdings import HoldingsScraper

    scraper = HoldingsScraper()
    print(f"Fetching shareholding data for {ticker}...")
    result = await scraper.scrape(ticker)
    return result


async def test_price(ticker: str, verbose: bool) -> dict:
    """Test the price scraper."""
    from workers.app.scrapers.price import PriceScraper

    scraper = PriceScraper()
    print(f"Fetching price data for {ticker}...")
    result = await scraper.scrape(ticker)
    return result


SCRAPERS = {
    "fundamentals": test_fundamentals,
    "technicals": test_technicals,
    "news": test_news,
    "holdings": test_holdings,
    "price": test_price,
}


async def run(ticker: str, scraper_name: str | None, verbose: bool) -> None:
    """Run the specified scraper(s) and print results."""
    scrapers_to_run = (
        {scraper_name: SCRAPERS[scraper_name]}
        if scraper_name
        else SCRAPERS
    )

    for name, func in scrapers_to_run.items():
        print(f"\n{'='*60}")
        print(f"  {name.upper()} — {ticker}")
        print(f"{'='*60}")

        start = datetime.now()
        try:
            result = await func(ticker, verbose)
            elapsed = (datetime.now() - start).total_seconds()
            print(f"\nCompleted in {elapsed:.2f}s")
            if verbose:
                print(json.dumps(result, indent=2, default=str))
            else:
                print(f"Result keys: {list(result.keys()) if isinstance(result, dict) else type(result).__name__}")
        except ImportError as e:
            print(f"\nScraper module not found: {e}")
            print("Make sure the workers package is installed.")
        except Exception as e:
            elapsed = (datetime.now() - start).total_seconds()
            print(f"\nFailed after {elapsed:.2f}s: {e}")
            if verbose:
                import traceback
                traceback.print_exc()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test Mr. Market scrapers for a given ticker"
    )
    parser.add_argument(
        "--ticker", "-t",
        required=True,
        help="NSE ticker symbol (e.g., RELIANCE, TCS, INFY)",
    )
    parser.add_argument(
        "--scraper", "-s",
        choices=list(SCRAPERS.keys()),
        default=None,
        help="Specific scraper to test (default: all)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print full result JSON",
    )
    args = parser.parse_args()

    asyncio.run(run(args.ticker.upper(), args.scraper, args.verbose))


if __name__ == "__main__":
    main()
