#!/usr/bin/env python3
"""Seed the stocks table with a representative set of Nifty 500 stocks.

Usage:
    python scripts/seed_universe.py

Requires DATABASE_URL environment variable to be set.
"""

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Ensure the shared package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mr_market_shared.db.models.stock import Stock  # noqa: E402

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://mrmarket:mrmarket@localhost:5432/mrmarket",
)

# Representative Nifty 500 stocks across sectors
SEED_STOCKS = [
    # Large-cap — Nifty 50
    {"ticker": "RELIANCE", "company_name": "Reliance Industries Ltd", "sector": "Oil & Gas", "industry": "Refineries", "cap": "Large", "is_nifty50": True, "is_nifty500": True, "is_fno": True},
    {"ticker": "TCS", "company_name": "Tata Consultancy Services Ltd", "sector": "IT", "industry": "IT Services", "cap": "Large", "is_nifty50": True, "is_nifty500": True, "is_fno": True},
    {"ticker": "HDFCBANK", "company_name": "HDFC Bank Ltd", "sector": "Banking", "industry": "Private Banks", "cap": "Large", "is_nifty50": True, "is_nifty500": True, "is_fno": True},
    {"ticker": "INFY", "company_name": "Infosys Ltd", "sector": "IT", "industry": "IT Services", "cap": "Large", "is_nifty50": True, "is_nifty500": True, "is_fno": True},
    {"ticker": "ICICIBANK", "company_name": "ICICI Bank Ltd", "sector": "Banking", "industry": "Private Banks", "cap": "Large", "is_nifty50": True, "is_nifty500": True, "is_fno": True},
    {"ticker": "HINDUNILVR", "company_name": "Hindustan Unilever Ltd", "sector": "FMCG", "industry": "FMCG", "cap": "Large", "is_nifty50": True, "is_nifty500": True, "is_fno": True},
    {"ticker": "BHARTIARTL", "company_name": "Bharti Airtel Ltd", "sector": "Telecom", "industry": "Telecom Services", "cap": "Large", "is_nifty50": True, "is_nifty500": True, "is_fno": True},
    {"ticker": "ITC", "company_name": "ITC Ltd", "sector": "FMCG", "industry": "Cigarettes & Tobacco", "cap": "Large", "is_nifty50": True, "is_nifty500": True, "is_fno": True},
    {"ticker": "SBIN", "company_name": "State Bank of India", "sector": "Banking", "industry": "Public Banks", "cap": "Large", "is_nifty50": True, "is_nifty500": True, "is_fno": True},
    {"ticker": "KOTAKBANK", "company_name": "Kotak Mahindra Bank Ltd", "sector": "Banking", "industry": "Private Banks", "cap": "Large", "is_nifty50": True, "is_nifty500": True, "is_fno": True},
    {"ticker": "LT", "company_name": "Larsen & Toubro Ltd", "sector": "Capital Goods", "industry": "Infrastructure", "cap": "Large", "is_nifty50": True, "is_nifty500": True, "is_fno": True},
    {"ticker": "AXISBANK", "company_name": "Axis Bank Ltd", "sector": "Banking", "industry": "Private Banks", "cap": "Large", "is_nifty50": True, "is_nifty500": True, "is_fno": True},
    # Mid-cap
    {"ticker": "TATAELXSI", "company_name": "Tata Elxsi Ltd", "sector": "IT", "industry": "IT Services", "cap": "Mid", "is_nifty50": False, "is_nifty500": True, "is_fno": True},
    {"ticker": "POLYCAB", "company_name": "Polycab India Ltd", "sector": "Capital Goods", "industry": "Cables", "cap": "Mid", "is_nifty50": False, "is_nifty500": True, "is_fno": True},
    {"ticker": "PERSISTENT", "company_name": "Persistent Systems Ltd", "sector": "IT", "industry": "IT Services", "cap": "Mid", "is_nifty50": False, "is_nifty500": True, "is_fno": True},
    # Small-cap
    {"ticker": "ROUTE", "company_name": "Route Mobile Ltd", "sector": "IT", "industry": "Cloud Communications", "cap": "Small", "is_nifty50": False, "is_nifty500": True, "is_fno": False},
    {"ticker": "KPITTECH", "company_name": "KPIT Technologies Ltd", "sector": "IT", "industry": "IT Services", "cap": "Small", "is_nifty50": False, "is_nifty500": True, "is_fno": True},
]


async def seed() -> None:
    """Insert seed stocks, skipping any that already exist."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Check which tickers already exist
        result = await session.execute(
            text("SELECT ticker FROM stocks WHERE ticker = ANY(:tickers)"),
            {"tickers": [s["ticker"] for s in SEED_STOCKS]},
        )
        existing = {row[0] for row in result.fetchall()}

        inserted = 0
        for stock_data in SEED_STOCKS:
            if stock_data["ticker"] in existing:
                print(f"  SKIP  {stock_data['ticker']} (already exists)")
                continue
            session.add(Stock(**stock_data))
            inserted += 1
            print(f"  ADD   {stock_data['ticker']}")

        await session.commit()
        print(f"\nSeeded {inserted} new stocks ({len(existing)} already existed).")

    await engine.dispose()


if __name__ == "__main__":
    print("Seeding stock universe...\n")
    asyncio.run(seed())
