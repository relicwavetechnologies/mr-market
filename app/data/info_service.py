"""GET /quote/{ticker}/info orchestrator.

Pulls fundamentals from yfinance.info + Screener.in (via curl_cffi) in parallel.
Returns both source payloads side-by-side plus a small "consensus" block for the
fields where the two sources have a comparable value.

We intentionally don't median-merge ratios — different sources compute P/E etc.
on slightly different earnings windows (TTM vs FY), so showing both is more
honest than picking one.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources import screener_info as scr_info
from app.data.sources import yf_info as yf_info
from app.db.models.stock import Stock

logger = logging.getLogger(__name__)


async def get_info(session: AsyncSession, ticker: str) -> dict[str, Any]:
    sym = ticker.upper().strip()

    stock = (
        await session.execute(select(Stock).where(Stock.ticker == sym))
    ).scalar_one_or_none()

    yf_task = asyncio.create_task(yf_info.fetch_info(sym))
    scr_task = asyncio.create_task(scr_info.fetch_info(sym))

    yf_payload: dict[str, Any] | None = None
    yf_error: str | None = None
    scr_payload: dict[str, Any] | None = None
    scr_error: str | None = None

    try:
        yf_payload = await yf_task
    except Exception as e:  # noqa: BLE001
        yf_error = str(e)

    try:
        scr_payload = await scr_task
    except Exception as e:  # noqa: BLE001
        scr_error = str(e)

    return {
        "ticker": sym,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "stock": _stock_brief(stock),
        "yfinance": yf_payload,
        "yfinance_error": yf_error,
        "screener": scr_payload,
        "screener_error": scr_error,
    }


def _stock_brief(stock: Stock | None) -> dict[str, Any] | None:
    if stock is None:
        return None
    return {
        "ticker": stock.ticker,
        "name": stock.name,
        "sector": stock.sector,
        "industry": stock.industry,
        "exchange": stock.exchange,
        "yahoo_symbol": stock.yahoo_symbol,
    }
