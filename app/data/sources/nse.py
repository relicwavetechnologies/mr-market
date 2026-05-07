"""NSE quote source.

Uses the public NSE JSON endpoints directly with a Chrome-like cookie warmup,
because (a) `nselib` is a sync wrapper that often lags upstream changes, and
(b) NSE's `bm_sv` / `_abck` cookies need a homepage-first request.

Endpoint:  https://www.nseindia.com/api/quote-equity?symbol=<TICKER>
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app.data.types import Quote, QuoteSourceError

_NSE_HOME = "https://www.nseindia.com"
_NSE_QUOTE_PAGE = "https://www.nseindia.com/get-quotes/equity?symbol={ticker}"
_NSE_QUOTE_API = "https://www.nseindia.com/api/quote-equity?symbol={ticker}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}


def _to_decimal(v: object) -> Decimal | None:
    if v is None or v == "" or v == "-":
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


async def fetch(ticker: str, *, timeout_s: float = 8.0) -> Quote:
    sym = ticker.upper()

    try:
        async with httpx.AsyncClient(
            headers=_HEADERS,
            timeout=timeout_s,
            follow_redirects=True,
        ) as client:
            # Warmup — NSE sets bm_sv/_abck on the home + the quote page.
            await client.get(_NSE_HOME)
            await client.get(_NSE_QUOTE_PAGE.format(ticker=sym))
            r = await client.get(_NSE_QUOTE_API.format(ticker=sym))

            if r.status_code in (401, 403):
                raise QuoteSourceError(f"NSE blocked ({r.status_code})")
            if r.status_code != 200:
                raise QuoteSourceError(f"NSE HTTP {r.status_code}")

            data = r.json()
    except httpx.TimeoutException as e:
        raise QuoteSourceError(f"NSE timeout after {timeout_s}s") from e
    except QuoteSourceError:
        raise
    except Exception as e:  # noqa: BLE001
        raise QuoteSourceError(f"NSE error: {e!s}") from e

    price_info = (data or {}).get("priceInfo") or {}
    if not price_info:
        raise QuoteSourceError("NSE: missing priceInfo")

    last = _to_decimal(price_info.get("lastPrice"))
    if last is None:
        raise QuoteSourceError("NSE: lastPrice missing")

    intraday = price_info.get("intraDayHighLow") or {}
    return Quote(
        ticker=sym,
        price=last,
        source="nselib",
        fetched_at=datetime.now(timezone.utc),
        prev_close=_to_decimal(price_info.get("previousClose")),
        day_open=_to_decimal(price_info.get("open")),
        day_high=_to_decimal(intraday.get("max")),
        day_low=_to_decimal(intraday.get("min")),
        volume=None,  # quote-equity does not expose volume directly
        extras={"vwap": str(price_info.get("vwap") or "")},
    )
