"""Screener.in fundamentals — scrape the company-page top-ratios block.

Returns whatever's available from Screener's `#top-ratios` UL: P/E, ROE, ROCE,
debt-to-equity, dividend yield, market cap. Values are kept as raw strings (no
unit conversion) when crore/lakh formatting is present, plus a parsed Decimal
where possible.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from bs4 import BeautifulSoup

from app.data.types import QuoteSourceError

_URL_CONS = "https://www.screener.in/company/{ticker}/consolidated/"
_URL_STAND = "https://www.screener.in/company/{ticker}/"

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")

_KEYS_OF_INTEREST = {
    "current price",
    "market cap",
    "stock p/e",
    "p/e",
    "book value",
    "dividend yield",
    "roce",
    "roe",
    "face value",
    "debt to equity",
    "high / low",
}


def _parse_number(raw: str) -> Decimal | None:
    if not raw:
        return None
    m = _NUM_RE.search(raw.replace(",", ""))
    if not m:
        return None
    try:
        return Decimal(m.group(0))
    except Exception:
        return None


def _fetch_sync(ticker: str, timeout_s: float) -> dict[str, Any]:
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
    fields: dict[str, Any] = {}

    for li in soup.select("ul#top-ratios li, ul.flex-row li, li"):
        name_el = li.find(class_="name")
        value_el = li.find(class_="value")
        if not name_el or not value_el:
            continue
        name = name_el.get_text(strip=True).lower().strip()
        if name not in _KEYS_OF_INTEREST:
            continue
        raw_text = value_el.get_text(" ", strip=True)
        parsed = _parse_number(raw_text)
        fields.setdefault(name, {"raw": raw_text, "value": str(parsed) if parsed is not None else None})

    return {
        "source": "screener",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "fields": fields,
    }


async def fetch_info(ticker: str, *, timeout_s: float = 10.0) -> dict[str, Any]:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_fetch_sync, ticker, timeout_s), timeout=timeout_s + 2
        )
    except asyncio.TimeoutError as e:
        raise QuoteSourceError(f"Screener.info timeout after {timeout_s}s") from e
    except QuoteSourceError:
        raise
    except Exception as e:  # noqa: BLE001
        raise QuoteSourceError(f"Screener.info error: {e!s}") from e
