"""NSE archive (`nsearchives.nseindia.com`) bhavcopy fetcher + parser.

URL pattern (post-2024 schema):
    https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip

CSV columns (relevant subset for equities):
    TradDt, TckrSymb, SctySrs, OpnPric, HghPric, LwPric, ClsPric,
    PrvsClsgPric, TtlTradgVol

Returns a list of `BhavRow` dataclasses (Decimal-typed) for any rows where
`SctySrs == 'EQ'` (regular equity series). Other series — BE, IL, SM, BZ — are
excluded; they share the symbol space and would corrupt our EOD bars table.

Failure semantics:
  * Weekend / holiday → 404 from NSE → we raise `BhavcopyMissing` so callers
    can `continue` rather than abort the backfill.
  * 403 / 5xx / network timeout → `BhavcopyFetchError` (transient).
  * Any other unexpected payload → `BhavcopyParseError`.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx

logger = logging.getLogger(__name__)

ARCHIVE_URL = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/zip,*/*",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.nseindia.com/",
}

# Required columns we consume. Built once for safety; if NSE removes one we
# fail loudly during parse rather than silently producing zeros.
REQUIRED_COLS = (
    "TradDt",
    "TckrSymb",
    "SctySrs",
    "OpnPric",
    "HghPric",
    "LwPric",
    "ClsPric",
    "PrvsClsgPric",
    "TtlTradgVol",
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BhavcopyError(Exception):
    """Base error for archive fetches."""


class BhavcopyMissing(BhavcopyError):
    """No bhavcopy for that date (weekend / holiday). Soft-skip in callers."""


class BhavcopyFetchError(BhavcopyError):
    """Transient fetch failure (network, 5xx, blocked)."""


class BhavcopyParseError(BhavcopyError):
    """Payload didn't match the expected schema."""


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class BhavRow:
    ticker: str
    trade_date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal
    prev_close: Decimal | None
    volume: int | None


# ---------------------------------------------------------------------------
# URL + date helpers
# ---------------------------------------------------------------------------


def url_for(d: date) -> str:
    """Build the archive URL for a given trade date (no validity check)."""
    return ARCHIVE_URL.format(ymd=d.strftime("%Y%m%d"))


# ---------------------------------------------------------------------------
# Parser (pure)
# ---------------------------------------------------------------------------


def _to_decimal(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    s = raw.strip()
    if not s or s == "-":
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _to_int(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(float(raw))  # tolerates "12345.0"
    except (TypeError, ValueError):
        return None


def parse_csv_bytes(
    body: bytes,
    *,
    universe: Iterable[str] | None = None,
) -> list[BhavRow]:
    """Parse a bhavcopy CSV (bytes) into BhavRow records.

    Args:
        body: raw CSV bytes (already extracted from the ZIP).
        universe: if given, only rows whose `TckrSymb` is in this set are kept.

    Raises:
        BhavcopyParseError: header missing required columns or no EQ rows.
    """
    text = body.decode("utf-8", errors="replace")
    # Strip any UTF-8 BOM / leading whitespace.
    text = text.lstrip("﻿").lstrip()

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise BhavcopyParseError("empty CSV — no header")
    missing = [c for c in REQUIRED_COLS if c not in reader.fieldnames]
    if missing:
        raise BhavcopyParseError(
            f"bhavcopy schema missing columns: {missing}; got {reader.fieldnames}"
        )

    # `universe is None` means "no filter" — keep every EQ row.
    # An empty container means "filter everything out" — keep zero rows.
    universe_upper = (
        {u.upper().strip() for u in universe} if universe is not None else None
    )
    out: list[BhavRow] = []
    skipped_non_eq = 0

    for raw in reader:
        if (raw.get("SctySrs") or "").strip() != "EQ":
            skipped_non_eq += 1
            continue
        ticker = (raw.get("TckrSymb") or "").strip().upper()
        if not ticker:
            continue
        if universe_upper is not None and ticker not in universe_upper:
            continue

        trad_dt_raw = (raw.get("TradDt") or "").strip()
        try:
            trade_date = date.fromisoformat(trad_dt_raw)
        except ValueError:
            # Malformed date — skip the row, never the whole file
            logger.warning("bhavcopy row %s: bad TradDt %r", ticker, trad_dt_raw)
            continue

        close = _to_decimal(raw.get("ClsPric"))
        if close is None:
            # No close = unusable row.
            continue

        out.append(
            BhavRow(
                ticker=ticker,
                trade_date=trade_date,
                open=_to_decimal(raw.get("OpnPric")),
                high=_to_decimal(raw.get("HghPric")),
                low=_to_decimal(raw.get("LwPric")),
                close=close,
                prev_close=_to_decimal(raw.get("PrvsClsgPric")),
                volume=_to_int(raw.get("TtlTradgVol")),
            )
        )

    logger.info(
        "bhavcopy parsed: %d EQ rows kept (universe=%s), %d non-EQ skipped",
        len(out),
        "all" if universe_upper is None else len(universe_upper),
        skipped_non_eq,
    )
    return out


def extract_zip(payload: bytes) -> bytes:
    """Open the ZIP and return the bytes of the (single) CSV inside.

    Bhavcopy ZIPs are flat and contain exactly one CSV; we don't go hunting
    if the archive structure changes — we fail loud.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_names:
                raise BhavcopyParseError(
                    f"ZIP has no CSV (members: {zf.namelist()})"
                )
            if len(csv_names) > 1:
                logger.warning("bhavcopy ZIP had >1 CSV: %s", csv_names)
            return zf.read(csv_names[0])
    except zipfile.BadZipFile as e:
        raise BhavcopyParseError(f"bad zip: {e!s}") from e


# ---------------------------------------------------------------------------
# Async fetch (network)
# ---------------------------------------------------------------------------


async def fetch_zip_bytes(d: date, *, timeout_s: float = 30.0) -> bytes:
    """Download the raw ZIP for one trade date. Raises on missing/transient/parse failures."""
    url = url_for(d)
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=timeout_s) as client:
            r = await client.get(url, follow_redirects=True)
    except httpx.TimeoutException as e:
        raise BhavcopyFetchError(f"timeout fetching {url}") from e
    except httpx.RequestError as e:
        raise BhavcopyFetchError(f"network error: {e!s}") from e

    if r.status_code == 404:
        raise BhavcopyMissing(f"no bhavcopy for {d.isoformat()} (weekend/holiday)")
    if r.status_code in (401, 403):
        raise BhavcopyFetchError(f"NSE blocked ({r.status_code}) for {d.isoformat()}")
    if r.status_code != 200:
        raise BhavcopyFetchError(f"HTTP {r.status_code} for {d.isoformat()}")

    if not r.content:
        raise BhavcopyParseError(f"empty body for {d.isoformat()}")

    return r.content


async def fetch_rows(
    d: date,
    *,
    universe: Iterable[str] | None = None,
    timeout_s: float = 30.0,
) -> list[BhavRow]:
    """Fetch + extract + parse for one trade date. Pipes the three steps."""
    zip_bytes = await fetch_zip_bytes(d, timeout_s=timeout_s)
    csv_bytes = extract_zip(zip_bytes)
    return parse_csv_bytes(csv_bytes, universe=universe)


# ---------------------------------------------------------------------------
# Date helpers — IST market calendar (weekday-only; holidays best-effort)
# ---------------------------------------------------------------------------


def likely_trading_day(d: date) -> bool:
    """True if `d` is a Mon-Fri (Indian market holidays not modelled here).

    The fetch path hands back BhavcopyMissing on holidays anyway, so this is
    just a cheap filter to avoid 404-bombing weekends.
    """
    return d.weekday() < 5


def utc_close_of_day(d: date) -> datetime:
    """End-of-day UTC timestamp for storage. NSE closes 15:30 IST = 10:00 UTC."""
    return datetime(d.year, d.month, d.day, 10, 0, 0, tzinfo=timezone.utc)
