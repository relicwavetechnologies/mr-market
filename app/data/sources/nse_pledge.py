"""NSE promoter-pledge fetcher.

Endpoint:
    https://www.nseindia.com/api/corporate-pledgedata?index=equities&symbol={TICKER}

Returns one row per quarter-end (shp date) with:
    percSharesPledged     → % of promoter holding pledged (headline number)
    percPromoterHolding   → promoter % of total equity (independent reading)
    numSharesPledged      → absolute share count pledged
    totPromoterHolding    → total promoter share count
    totIssuedShares       → total equity outstanding
    broadcastDt           → e.g. '07-May-2026 16:30:21'

We surface the latest reading + a small "risk_band" qualitative tag so the
LLM can reason about it without hard-coding thresholds in the prompt:

    band      condition                use case
    -----     ---------                --------
    low       pledged <  5%            informational
    moderate  5% ≤ pledged < 10%       worth mentioning
    elevated  10% ≤ pledged < 25%      flag in analyst view
    high      ≥ 25%                    flag prominently

Intentionally narrow scope: this is a drill-down on the existing holding
data, not a new top-level pipeline. Failures (network, schema drift)
return None — the caller (`get_holding`) tolerates pledge data missing
and degrades gracefully.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import httpx

from app.data.sources.nse_shareholding import _parse_dd_mon_yyyy

logger = logging.getLogger(__name__)

API_URL = (
    "https://www.nseindia.com/api/corporate-pledgedata"
    "?index=equities&symbol={ticker}"
)
HOMEPAGE_URL = "https://www.nseindia.com/"
LANDING_URL = (
    "https://www.nseindia.com/companies-listing/corporate-filings-pledged-data"
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


@dataclass(slots=True, frozen=True)
class PledgeRow:
    ticker: str
    quarter_end: date
    promoter_pct: Decimal | None       # % of equity held by promoters
    pledged_pct: Decimal | None        # % of promoter holding that is pledged
    num_shares_pledged: int | None     # absolute count
    total_promoter_shares: int | None
    total_issued_shares: int | None
    broadcast_at: datetime | None
    risk_band: str                     # low | moderate | elevated | high | unknown


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


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
    if d < 0 or d > 100:
        return None
    return d


def _parse_int(v: object) -> int | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s or s == "-":
        return None
    try:
        return int(Decimal(s))
    except (InvalidOperation, ValueError):
        return None


def _parse_broadcast(raw: str | None) -> datetime | None:
    """`broadcastDt` is like '07-May-2026 16:30:21' (24h)."""
    if not raw:
        return None
    s = raw.strip()
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _band(pledged_pct: Decimal | None) -> str:
    if pledged_pct is None:
        return "unknown"
    p = float(pledged_pct)
    if p < 5:
        return "low"
    if p < 10:
        return "moderate"
    if p < 25:
        return "elevated"
    return "high"


def parse_records(ticker: str, payload: object) -> list[PledgeRow]:
    """Pure parser. Defensive: silently drops malformed rows; never raises
    on shape — only on outright wrong type."""
    if not isinstance(payload, dict):
        return []
    items = payload.get("data")
    if not isinstance(items, list):
        return []

    sym = ticker.upper().strip()
    out: list[PledgeRow] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        # NSE encodes the quarter as 'shp' (e.g. '31-Mar-2026').
        # Their parser is case-sensitive on the month abbrev so normalise.
        shp = raw.get("shp")
        if isinstance(shp, str):
            shp_upper = shp.upper()
        else:
            shp_upper = None
        q = _parse_dd_mon_yyyy(shp_upper)
        if q is None:
            continue
        pledged_pct = _parse_pct(raw.get("percSharesPledged"))
        out.append(
            PledgeRow(
                ticker=sym,
                quarter_end=q,
                promoter_pct=_parse_pct(raw.get("percPromoterHolding")),
                pledged_pct=pledged_pct,
                num_shares_pledged=_parse_int(raw.get("numSharesPledged")),
                total_promoter_shares=_parse_int(raw.get("totPromoterHolding")),
                total_issued_shares=_parse_int(raw.get("totIssuedShares")),
                broadcast_at=_parse_broadcast(raw.get("broadcastDt")),
                risk_band=_band(pledged_pct),
            )
        )
    # Sort latest first by quarter, tie-break on broadcast time.
    out.sort(
        key=lambda r: (r.quarter_end, r.broadcast_at or datetime.min),
        reverse=True,
    )
    return out


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------


async def fetch(ticker: str, *, timeout_s: float = 15.0) -> list[PledgeRow]:
    """Pull pledge disclosures for `ticker`. Empty list if NSE returns no
    data (e.g. brand-new listing). Raises only on transport / 5xx errors —
    callers should `try/except` and treat exceptions as "pledge unavailable".
    """
    sym = ticker.upper().strip()
    url = API_URL.format(ticker=sym)

    async with httpx.AsyncClient(headers=_HEADERS, timeout=timeout_s) as client:
        # NSE wants cookies from homepage + landing page warmup.
        await client.get(HOMEPAGE_URL)
        await client.get(LANDING_URL)
        r = await client.get(url)

    if r.status_code in (401, 403):
        raise RuntimeError(f"NSE blocked ({r.status_code}) for {sym}")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} for {sym}")

    try:
        payload = r.json()
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"non-JSON pledge body: {e!s}") from e

    return parse_records(sym, payload)
