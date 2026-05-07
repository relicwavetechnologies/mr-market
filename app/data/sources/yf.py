"""Yahoo Finance quote source via the `yfinance` library.

Runs the synchronous yfinance call inside `asyncio.to_thread` so we don't block
the event loop. yfinance for `.NS` symbols hits Yahoo's public API and is the
most reliable single source for Indian stocks (NSE).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import yfinance as yf

from app.data.types import Quote, QuoteSourceError


def _yahoo_symbol(ticker: str) -> str:
    """RELIANCE -> RELIANCE.NS. Idempotent if already suffixed."""
    if "." in ticker:
        return ticker
    return f"{ticker}.NS"


def _to_decimal(v: object) -> Decimal | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN check
        return None
    return Decimal(str(round(f, 4)))


def _fetch_sync(ticker: str) -> Quote:
    sym = _yahoo_symbol(ticker)
    t = yf.Ticker(sym)

    # fast_info is the cheap path (no full .info dict); falls back to history if absent.
    fi = getattr(t, "fast_info", None)
    last_price = None
    prev_close = None
    day_open = None
    day_high = None
    day_low = None
    volume = None

    if fi is not None:
        try:
            last_price = _to_decimal(fi.get("last_price") if hasattr(fi, "get") else fi.last_price)
        except Exception:
            last_price = None
        try:
            prev_close = _to_decimal(
                fi.get("previous_close") if hasattr(fi, "get") else fi.previous_close
            )
        except Exception:
            prev_close = None
        try:
            day_open = _to_decimal(fi.get("open") if hasattr(fi, "get") else fi.open)
        except Exception:
            day_open = None
        try:
            day_high = _to_decimal(fi.get("day_high") if hasattr(fi, "get") else fi.day_high)
        except Exception:
            day_high = None
        try:
            day_low = _to_decimal(fi.get("day_low") if hasattr(fi, "get") else fi.day_low)
        except Exception:
            day_low = None
        try:
            v = fi.get("last_volume") if hasattr(fi, "get") else fi.last_volume
            volume = int(v) if v is not None else None
        except Exception:
            volume = None

    if last_price is None:
        # Fallback: pull a 1-day history.
        hist = t.history(period="1d", auto_adjust=False)
        if hist is None or hist.empty:
            raise QuoteSourceError(f"yfinance returned no data for {sym}")
        last_price = _to_decimal(hist["Close"].iloc[-1])
        if day_open is None:
            day_open = _to_decimal(hist["Open"].iloc[-1])
        if day_high is None:
            day_high = _to_decimal(hist["High"].iloc[-1])
        if day_low is None:
            day_low = _to_decimal(hist["Low"].iloc[-1])
        if volume is None and "Volume" in hist:
            try:
                volume = int(hist["Volume"].iloc[-1])
            except Exception:
                volume = None

    if last_price is None:
        raise QuoteSourceError(f"yfinance: no last_price for {sym}")

    return Quote(
        ticker=ticker,
        price=last_price,
        source="yfinance",
        fetched_at=datetime.now(timezone.utc),
        prev_close=prev_close,
        day_open=day_open,
        day_high=day_high,
        day_low=day_low,
        volume=volume,
        extras={"yahoo_symbol": sym},
    )


async def fetch(ticker: str, *, timeout_s: float = 8.0) -> Quote:
    """Async wrapper. Raises QuoteSourceError on failure."""
    try:
        return await asyncio.wait_for(asyncio.to_thread(_fetch_sync, ticker), timeout=timeout_s)
    except asyncio.TimeoutError as e:
        raise QuoteSourceError(f"yfinance timeout after {timeout_s}s") from e
    except QuoteSourceError:
        raise
    except Exception as e:  # noqa: BLE001
        raise QuoteSourceError(f"yfinance error: {e!s}") from e
