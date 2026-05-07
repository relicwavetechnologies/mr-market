"""yfinance fundamentals — pull `.info` (or `.get_info()`) for one ticker."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import yfinance as yf

from app.data.types import QuoteSourceError


def _to_decimal(v: object) -> Decimal | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return Decimal(str(round(f, 4)))


def _yahoo_symbol(ticker: str) -> str:
    return ticker if "." in ticker else f"{ticker}.NS"


def _fetch_sync(ticker: str) -> dict[str, Any]:
    sym = _yahoo_symbol(ticker)
    t = yf.Ticker(sym)
    try:
        info = t.get_info()
    except Exception as e:  # noqa: BLE001
        raise QuoteSourceError(f"yfinance.get_info: {e!s}") from e
    if not isinstance(info, dict) or not info:
        raise QuoteSourceError(f"yfinance: empty info for {sym}")

    # Return a small, named subset. Skip anything we don't actively use.
    return {
        "source": "yfinance",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "yahoo_symbol": sym,
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_cap": _str_or_none(_to_decimal(info.get("marketCap"))),
        "pe_trailing": _str_or_none(_to_decimal(info.get("trailingPE"))),
        "pe_forward": _str_or_none(_to_decimal(info.get("forwardPE"))),
        "price_to_book": _str_or_none(_to_decimal(info.get("priceToBook"))),
        "dividend_yield": _str_or_none(_to_decimal(info.get("dividendYield"))),
        "beta": _str_or_none(_to_decimal(info.get("beta"))),
        "fifty_two_week_high": _str_or_none(_to_decimal(info.get("fiftyTwoWeekHigh"))),
        "fifty_two_week_low": _str_or_none(_to_decimal(info.get("fiftyTwoWeekLow"))),
        "shares_outstanding": _str_or_none(_to_decimal(info.get("sharesOutstanding"))),
        "currency": info.get("currency"),
    }


def _str_or_none(v: Decimal | None) -> str | None:
    return str(v) if v is not None else None


async def fetch_info(ticker: str, *, timeout_s: float = 10.0) -> dict[str, Any]:
    try:
        return await asyncio.wait_for(asyncio.to_thread(_fetch_sync, ticker), timeout=timeout_s)
    except asyncio.TimeoutError as e:
        raise QuoteSourceError(f"yfinance.info timeout after {timeout_s}s") from e
    except QuoteSourceError:
        raise
    except Exception as e:  # noqa: BLE001
        raise QuoteSourceError(f"yfinance.info error: {e!s}") from e
