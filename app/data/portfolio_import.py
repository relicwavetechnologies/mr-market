"""Portfolio CSV + Zerodha CDSL paste parsers (P3-A4).

The endpoint accepts EITHER:
- A pre-parsed `holdings` array (`[{ticker, quantity, avg_price}, ...]`),
  e.g. from a frontend that already parsed the file. This is the canonical
  path locked in `app/contracts/phase3.md`.
- A `raw_text` blob — the user pasted their Zerodha holdings page or
  uploaded a CSV. The server detects the format and parses it here.

Both paths flow through `validate_holdings()` which enforces:
- Tickers must exist in the active `stocks` universe (NIFTY-100 today).
- Quantities are positive integers; bad rows are dropped with a warning.
- Repeated rows for the same ticker are collapsed (sum qty, weighted-avg cost).

The parser is intentionally tolerant — Zerodha's copy-paste output varies
across browsers, and the CSV format isn't standardised. We trust the
server-side ticker check to reject anything that doesn't resolve.
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable


@dataclass(slots=True, frozen=True)
class ParsedHolding:
    ticker: str
    quantity: int
    avg_price: Decimal | None = None


@dataclass(slots=True)
class ParseReport:
    """Carry-along for warnings the API can surface to the user."""

    holdings: list[ParsedHolding]
    skipped_rows: list[str]
    detected_format: str


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


_CSV_HEADER_HINTS = re.compile(
    r"\b(ticker|symbol|instrument|qty|quantity|avg[\s_]?cost|avg[\s_]?price)\b",
    re.IGNORECASE,
)


def detect_format(text: str) -> str:
    """Return `"csv"` or `"cdsl_paste"` based on shape heuristics. CSV
    files have commas; the Zerodha holdings page paste is whitespace-
    or tab-delimited with a typical header row."""
    head = "\n".join(text.splitlines()[:3])
    if "," in head and head.count(",") >= 2:
        return "csv"
    return "cdsl_paste"


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


_TICKER_KEYS = ("ticker", "symbol", "instrument", "scrip")
_QTY_KEYS = ("quantity", "qty", "shares", "qty.")
_AVG_KEYS = ("avg_price", "avg price", "avg cost", "avg_cost", "average cost", "price")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _find_col(header: list[str], candidates: tuple[str, ...]) -> int | None:
    norm = [_norm(h) for h in header]
    for cand in candidates:
        c = _norm(cand)
        for i, h in enumerate(norm):
            if h == c:
                return i
        # Substring fallback for "Avg cost" → "avgcost".
        for i, h in enumerate(norm):
            if c in h:
                return i
    return None


def _parse_qty(s: str) -> int | None:
    s = s.strip().replace(",", "").replace("'", "")
    if not s:
        return None
    try:
        n = int(float(s))
        return n if n > 0 else None
    except (ValueError, TypeError):
        return None


def _parse_decimal(s: str) -> Decimal | None:
    s = (s or "").strip().replace(",", "").replace("'", "")
    if not s or s.lower() in {"-", "n/a", "na"}:
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return d if d > 0 else None


def parse_csv(text: str) -> ParseReport:
    """Parse a CSV blob. Header is expected on row 1; we look up the
    ticker / quantity / avg-price columns by name. Rows we can't parse
    are added to `skipped_rows` with a short reason."""
    skipped: list[str] = []
    holdings: list[ParsedHolding] = []

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return ParseReport(holdings=[], skipped_rows=["empty input"], detected_format="csv")

    header = [c.strip() for c in rows[0]]
    t_idx = _find_col(header, _TICKER_KEYS)
    q_idx = _find_col(header, _QTY_KEYS)
    a_idx = _find_col(header, _AVG_KEYS)

    if t_idx is None or q_idx is None:
        return ParseReport(
            holdings=[],
            skipped_rows=[
                f"could not find ticker / quantity column in header {header!r}"
            ],
            detected_format="csv",
        )

    for ix, raw in enumerate(rows[1:], start=2):
        if not raw or all(not c.strip() for c in raw):
            continue
        try:
            ticker = raw[t_idx].strip().upper()
            qty = _parse_qty(raw[q_idx])
            avg = _parse_decimal(raw[a_idx]) if a_idx is not None and a_idx < len(raw) else None
        except IndexError:
            skipped.append(f"row {ix}: too few columns")
            continue
        if not ticker:
            skipped.append(f"row {ix}: blank ticker")
            continue
        if qty is None:
            skipped.append(f"row {ix} ({ticker}): bad quantity")
            continue
        holdings.append(ParsedHolding(ticker=ticker, quantity=qty, avg_price=avg))

    return ParseReport(holdings=holdings, skipped_rows=skipped, detected_format="csv")


# ---------------------------------------------------------------------------
# Zerodha CDSL paste
# ---------------------------------------------------------------------------


# Tolerant of:
#   "RELIANCE   100   1280.50   1436.10   ..."        (whitespace)
#   "RELIANCE\t100\t1280.50\t1436.10\t..."             (tab-delimited)
#   "RELIANCE  100  ₹1,280.50  ..."                    (with rupee + comma)
_PASTE_HEADER_TOKENS = {
    "instrument",
    "symbol",
    "ticker",
    "scrip",
    "qty",
    "quantity",
    "avg",
    "ltp",
    "cur",
    "value",
    "p&l",
    "net",
    "chg",
    "cost",
    "investment",
    "current",
    "isin",
}


def _looks_like_header(tokens: list[str]) -> bool:
    """True if the line is a Zerodha-style header row (instrument / qty /
    avg cost / ltp / etc.)."""
    head = " ".join(tokens).lower()
    return sum(1 for t in _PASTE_HEADER_TOKENS if t in head) >= 2


def parse_cdsl_paste(text: str) -> ParseReport:
    """Parse a free-form Zerodha holdings paste. Each line is split on
    tabs / runs of whitespace; we look for a leading ticker (alphanumeric,
    uppercased), then the first numeric token as quantity, then the next
    decimal-looking token as avg cost."""
    skipped: list[str] = []
    holdings: list[ParsedHolding] = []

    for ix, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        # Split on tabs first (CDSL paste from Zerodha sometimes uses
        # \t, sometimes runs of whitespace).
        parts = [p.strip() for p in (line.split("\t") if "\t" in line else line.split())]
        if len(parts) < 2:
            continue
        if _looks_like_header(parts):
            continue

        # First token = ticker candidate. Allow `BAJAJ-AUTO`, `M&M`, etc.
        ticker = parts[0].upper()
        if not re.match(r"^[A-Z0-9&\-\.]+$", ticker) or len(ticker) > 32:
            skipped.append(f"line {ix}: ticker {parts[0]!r} doesn't look like an NSE symbol")
            continue
        # Drop ISIN-leading lines (12-char alphanumeric → no NSE symbol).
        if len(ticker) == 12 and ticker.isalnum() and ticker[:2].isalpha():
            skipped.append(f"line {ix}: looks like an ISIN, not a ticker")
            continue

        qty: int | None = None
        avg: Decimal | None = None
        for tok in parts[1:]:
            # Strip ₹, commas, asterisks, sign markers.
            cleaned = re.sub(r"[₹,'*]", "", tok).strip()
            if cleaned.startswith("+") or cleaned.startswith("-"):
                cleaned = cleaned[1:]
            if not cleaned:
                continue
            if qty is None:
                # First numeric integer token → quantity.
                if re.fullmatch(r"\d+", cleaned):
                    n = int(cleaned)
                    if n > 0:
                        qty = n
                continue
            # Second numeric token (decimal allowed) → avg cost.
            if re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
                d = Decimal(cleaned)
                if d > 0:
                    avg = d
                break

        if qty is None:
            skipped.append(f"line {ix} ({ticker}): no quantity found")
            continue
        holdings.append(ParsedHolding(ticker=ticker, quantity=qty, avg_price=avg))

    return ParseReport(
        holdings=holdings, skipped_rows=skipped, detected_format="cdsl_paste"
    )


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def parse_text(text: str, *, format: str | None = None) -> ParseReport:
    """Parse a free-form text blob in either CSV or CDSL-paste format.
    `format` overrides auto-detection when set (`"csv"` | `"cdsl_paste"`).
    """
    fmt = format or detect_format(text)
    if fmt == "csv":
        return parse_csv(text)
    if fmt == "cdsl_paste":
        return parse_cdsl_paste(text)
    raise ValueError(f"unknown format: {fmt!r}")


def collapse_duplicates(items: Iterable[ParsedHolding]) -> list[ParsedHolding]:
    """Merge repeated rows for the same ticker. Quantity sums; avg-price
    is the weighted average across the inputs (or None if no row had one)."""
    by_ticker: dict[str, list[ParsedHolding]] = defaultdict(list)
    for h in items:
        by_ticker[h.ticker].append(h)

    out: list[ParsedHolding] = []
    for ticker, group in by_ticker.items():
        total_qty = sum(g.quantity for g in group)
        priced = [(g.quantity, g.avg_price) for g in group if g.avg_price is not None]
        if priced:
            num = sum(q * p for q, p in priced)
            den = sum(q for q, _ in priced)
            avg = (num / den) if den else None
        else:
            avg = None
        out.append(
            ParsedHolding(ticker=ticker, quantity=total_qty, avg_price=avg)
        )
    return out
