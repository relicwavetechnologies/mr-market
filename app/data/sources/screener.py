"""Screener.in quote source — scrapes the company page header.

Uses curl_cffi with a Chrome TLS fingerprint to get past Cloudflare. Read-only,
respects robots-style courtesy: one request per call, no aggressive retries.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from decimal import Decimal

from bs4 import BeautifulSoup

from app.data.types import Quote, QuoteSourceError

_URL_CONS = "https://www.screener.in/company/{ticker}/consolidated/"
_URL_STAND = "https://www.screener.in/company/{ticker}/"

_NUM_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*")


def _parse_currency(text: str) -> Decimal | None:
    text = text.replace("₹", "").replace(",", "").strip()
    m = _NUM_RE.search(text)
    if not m:
        return None
    try:
        return Decimal(m.group(0).replace(",", ""))
    except Exception:
        return None


def _fetch_sync(ticker: str, timeout_s: float) -> Quote:
    # Lazy import keeps cold-start cheap if Screener isn't called.
    from curl_cffi import requests as cf_requests

    sym = ticker.upper()
    last_err: Exception | None = None
    html: str | None = None

    for url in (_URL_CONS.format(ticker=sym), _URL_STAND.format(ticker=sym)):
        try:
            r = cf_requests.get(
                url,
                impersonate="chrome124",
                timeout=timeout_s,
                headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            if r.status_code == 404:
                last_err = QuoteSourceError(f"Screener 404 for {sym}")
                continue
            if r.status_code in (401, 403, 503):
                raise QuoteSourceError(f"Screener blocked ({r.status_code})")
            if r.status_code != 200:
                raise QuoteSourceError(f"Screener HTTP {r.status_code}")
            html = r.text
            break
        except QuoteSourceError as e:
            last_err = e
        except Exception as e:  # noqa: BLE001
            last_err = QuoteSourceError(f"Screener error: {e!s}")

    if html is None:
        raise last_err or QuoteSourceError("Screener: no response")

    soup = BeautifulSoup(html, "lxml")

    # Current price lives in the company-info top section.
    # Note: Screener's "High / Low" on the landing page is 52-WEEK, not day,
    # so we deliberately do NOT scrape it — would mislead our cross-validator.
    price: Decimal | None = None
    for li in soup.select("ul#top-ratios li, ul.flex-row li, li"):
        name_el = li.find(class_="name")
        value_el = li.find(class_="value")
        if not name_el or not value_el:
            continue
        name = name_el.get_text(strip=True).lower()
        if "current price" in name:
            price = _parse_currency(value_el.get_text(" ", strip=True))
            break

    if price is None:
        raise QuoteSourceError("Screener: could not parse current price")

    return Quote(
        ticker=sym,
        price=price,
        source="screener",
        fetched_at=datetime.now(timezone.utc),
        prev_close=None,
        day_open=None,
        day_high=None,
        day_low=None,
        volume=None,
    )


async def fetch(ticker: str, *, timeout_s: float = 10.0) -> Quote:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_fetch_sync, ticker, timeout_s), timeout=timeout_s + 2
        )
    except asyncio.TimeoutError as e:
        raise QuoteSourceError(f"Screener timeout after {timeout_s}s") from e
    except QuoteSourceError:
        raise
    except Exception as e:  # noqa: BLE001
        raise QuoteSourceError(f"Screener error: {e!s}") from e
