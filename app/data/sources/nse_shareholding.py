"""NSE quarterly shareholding pattern fetcher.

Endpoint:
    https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol={TICKER}

Returns an array of quarterly filings, each with:
    date          → "31-MAR-2026" (quarter end)
    pr_and_prgrp  → promoter & promoter group total %
    public_val    → public total %
    employeeTrusts → employee trust % (held by ESOP / similar)
    xbrl          → URL of the detailed XBRL filing (we don't parse it
                    here — surface it for downstream tools)
    submissionDate / broadcastDate

We capture the top-level summary plus a JSON blob of the full original
record so future code can drill into the XBRL without changing the schema.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

logger = logging.getLogger(__name__)

API_URL = (
    "https://www.nseindia.com/api/corporate-share-holdings-master"
    "?index=equities&symbol={ticker}"
)
HOMEPAGE_URL = "https://www.nseindia.com/"
LANDING_URL = (
    "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern"
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json,*/*",
    "Accept-Encoding": "gzip, deflate",
    "Referer": LANDING_URL,
}


# ---------------------------------------------------------------------------
# Types + errors
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class HoldingRow:
    ticker: str
    quarter_end: date
    promoter_pct: Decimal | None
    public_pct: Decimal | None
    employee_trust_pct: Decimal | None
    xbrl_url: str | None
    submission_date: date | None
    broadcast_date: date | None
    raw: dict[str, Any] = field(default_factory=dict)


class ShareholdingError(Exception):
    """Base error."""


class ShareholdingMissing(ShareholdingError):
    """Symbol returned an empty array (ticker not covered or post-corporate-action)."""


class ShareholdingFetchError(ShareholdingError):
    """Transient network / NSE-blocked error."""


class ShareholdingParseError(ShareholdingError):
    """Payload didn't look like the expected schema."""


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def _parse_dd_mon_yyyy(raw: str | None) -> date | None:
    """NSE encodes dates as e.g. '31-MAR-2026'. Defensive parse: returns
    None on any malformed input rather than raising."""
    if not raw or not isinstance(raw, str):
        return None
    parts = raw.strip().upper().split("-")
    if len(parts) != 3:
        return None
    try:
        d, mon, y = parts
        return date(int(y), _MONTHS[mon], int(d))
    except (KeyError, ValueError):
        return None


def _parse_pct(v: object) -> Decimal | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s == "-":
        return None
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    # Sanity: percentages must be 0..100 — drop garbage.
    if d < 0 or d > 100:
        return None
    return d


def _broadcast_to_date(raw: str | None) -> date | None:
    """`broadcastDate` can be 'DD-MON-YYYY HH:MM:SS' OR 'DD-MON-YYYY'."""
    if not raw:
        return None
    head = raw.strip().split(" ", 1)[0]
    return _parse_dd_mon_yyyy(head)


def parse_records(ticker: str, payload: object) -> list[HoldingRow]:
    """Pure parser. Raises `ShareholdingParseError` on the wrong shape;
    returns [] for an empty array (ticker has no filings)."""
    if not isinstance(payload, list):
        raise ShareholdingParseError(
            f"shareholding payload not a list (got {type(payload).__name__})"
        )

    out: list[HoldingRow] = []
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        q = _parse_dd_mon_yyyy(raw.get("date"))
        if q is None:
            # Skip rows with unparseable quarter dates rather than aborting.
            continue
        out.append(
            HoldingRow(
                ticker=ticker.upper(),
                quarter_end=q,
                promoter_pct=_parse_pct(raw.get("pr_and_prgrp")),
                public_pct=_parse_pct(raw.get("public_val")),
                employee_trust_pct=_parse_pct(raw.get("employeeTrusts")),
                xbrl_url=(raw.get("xbrl") if isinstance(raw.get("xbrl"), str) else None),
                submission_date=_parse_dd_mon_yyyy(raw.get("submissionDate")),
                broadcast_date=_broadcast_to_date(raw.get("broadcastDate")),
                raw=raw,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Async fetcher (cookie warmup + JSON GET)
# ---------------------------------------------------------------------------


async def fetch(ticker: str, *, timeout_s: float = 30.0) -> list[HoldingRow]:
    """Pull every quarterly shareholding row NSE has on file for `ticker`.

    Idempotent (NSE filings don't mutate after publication, modulo rare
    revisions — handled by upsert on (ticker, quarter_end)).

    Failure semantics:
      ShareholdingMissing  — empty array. Caller should soft-skip.
      ShareholdingFetchError — transient. Cron retries next night.
      ShareholdingParseError — schema drift. Fail loud.
    """
    sym = ticker.upper().strip()
    url = API_URL.format(ticker=sym)

    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=timeout_s) as client:
            # Warmup — NSE sets bm_sv/_abck cookies on the homepage.
            await client.get(HOMEPAGE_URL)
            await client.get(LANDING_URL)
            r = await client.get(url)
    except httpx.TimeoutException as e:
        raise ShareholdingFetchError(f"timeout fetching {url}") from e
    except httpx.RequestError as e:
        raise ShareholdingFetchError(f"network error: {e!s}") from e

    if r.status_code in (401, 403):
        raise ShareholdingFetchError(f"NSE blocked ({r.status_code}) for {sym}")
    if r.status_code != 200:
        raise ShareholdingFetchError(f"HTTP {r.status_code} for {sym}")

    try:
        payload = r.json()
    except Exception as e:  # noqa: BLE001
        raise ShareholdingParseError(f"non-JSON body: {e!s}") from e

    rows = parse_records(sym, payload)
    if not rows:
        raise ShareholdingMissing(f"no shareholding rows for {sym}")
    return rows


# ---------------------------------------------------------------------------
# Pure helpers used by the API for QoQ delta computation
# ---------------------------------------------------------------------------


def quarter_label(d: date) -> str:
    """Return e.g. 'Q4 FY26' for a quarter-end date.

    Indian FY runs Apr-Mar. Q4 ends 31-MAR; Q1 ends 30-JUN; Q2 = 30-SEP; Q3 = 31-DEC.
    """
    m = d.month
    if m == 3:
        return f"Q4 FY{d.year % 100:02d}"
    if m == 6:
        return f"Q1 FY{(d.year + 1) % 100:02d}"
    if m == 9:
        return f"Q2 FY{(d.year + 1) % 100:02d}"
    if m == 12:
        return f"Q3 FY{(d.year + 1) % 100:02d}"
    # Non-quarterly date — return ISO.
    return d.isoformat()


def utc_day_at(d: date) -> datetime:
    """Stable UTC datetime for a quarter-end date — used if we ever need
    to sort by datetime instead of date."""
    return datetime(d.year, d.month, d.day)
