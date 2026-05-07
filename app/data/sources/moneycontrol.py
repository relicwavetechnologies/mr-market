"""Moneycontrol quote source.

MC exposes a JSON pricefeed at:
    https://priceapi.moneycontrol.com/pricefeed/nse/equitycash/<MC_CODE>

It needs MC's internal `sc_id` (e.g. RELIANCE -> "RI"), not the NSE symbol.
MC's public `autosuggesion.php` endpoint returns HTML (not JSON) without an
authenticated session, so we use a static NSE→MC code map for our universe.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app.data.sources.moneycontrol_codes import NSE_TO_MC
from app.data.types import Quote, QuoteSourceError

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.moneycontrol.com/",
}

_PRICEFEED = "https://priceapi.moneycontrol.com/pricefeed/nse/equitycash/{mc_code}"


def _to_decimal(s: object) -> Decimal | None:
    if s is None or s == "":
        return None
    text = str(s).replace(",", "").strip()
    if not text or text == "-":
        return None
    try:
        return Decimal(text)
    except Exception:
        return None


def _safe_int(v: object) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(str(v).replace(",", ""))
    except Exception:
        return None


async def fetch(ticker: str, *, timeout_s: float = 8.0) -> Quote:
    sym = ticker.upper().strip()
    mc_code = NSE_TO_MC.get(sym)
    if not mc_code:
        raise QuoteSourceError(f"MC: no sc_id for {sym} (add to moneycontrol_codes.py)")

    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=timeout_s) as client:
            r = await client.get(_PRICEFEED.format(mc_code=mc_code))
            if r.status_code != 200:
                raise QuoteSourceError(f"MC pricefeed HTTP {r.status_code}")
            payload = r.json()
    except httpx.TimeoutException as e:
        raise QuoteSourceError(f"MC timeout after {timeout_s}s") from e
    except QuoteSourceError:
        raise
    except Exception as e:  # noqa: BLE001
        raise QuoteSourceError(f"MC error: {e!s}") from e

    if not isinstance(payload, dict):
        raise QuoteSourceError("MC pricefeed: bad JSON")

    if str(payload.get("code")) != "200":
        raise QuoteSourceError(f"MC: {payload.get('message') or 'no data'}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise QuoteSourceError("MC pricefeed: missing data")

    last = _to_decimal(data.get("pricecurrent"))
    if last is None:
        raise QuoteSourceError("MC pricefeed: no pricecurrent")

    return Quote(
        ticker=sym,
        price=last,
        source="moneycontrol",
        fetched_at=datetime.now(timezone.utc),
        prev_close=_to_decimal(data.get("priceprevclose")),
        day_open=_to_decimal(data.get("OPN")),
        day_high=_to_decimal(data.get("HP")),
        day_low=_to_decimal(data.get("LP")),
        volume=_safe_int(data.get("VOL")),
        extras={"mc_code": mc_code},
    )
