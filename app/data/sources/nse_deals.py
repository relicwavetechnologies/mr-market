"""NSE bulk + block deals — pulled via `nselib.capital_market`.

Bulk deals: any single transaction ≥ 0.5 % of the listed company's equity
   (most often by FIIs / DIIs / large traders).
Block deals: deals routed through the special block window (typically
   institutional cross-trades, with a hard ₹10 cr trade-value floor).

Both come back from nselib as one flat DataFrame per call. The library hides
NSE's auth / cookie dance under the hood, which is precisely why we let it
own that surface area instead of coding it ourselves.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

import pandas as pd

logger = logging.getLogger(__name__)

DealKind = Literal["bulk", "block"]


@dataclass(slots=True, frozen=True)
class DealRow:
    trade_date: date
    symbol: str
    security_name: str
    client_name: str
    side: str            # "BUY" | "SELL"
    quantity: int
    avg_price: Decimal
    remarks: str | None
    kind: DealKind


class DealsError(Exception):
    """Base for deals-source errors."""


class DealsFetchError(DealsError):
    """Transient fetch failure (network, NSE blocked)."""


class DealsParseError(DealsError):
    """nselib returned a frame we don't recognise."""


# --- columns we expect from nselib (bulk and block share the same schema) --
EXPECTED_COLS = {
    "Date",
    "Symbol",
    "SecurityName",
    "ClientName",
    "Buy/Sell",
    "QuantityTraded",
    "TradePrice/Wght.Avg.Price",
}


# ---------------------------------------------------------------------------
# Parsers (pure)
# ---------------------------------------------------------------------------


_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def _parse_dd_mon_yyyy(raw: str | None) -> date | None:
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


def _parse_int(raw) -> int | None:
    if raw is None:
        return None
    s = str(raw).replace(",", "").strip()
    if not s:
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _parse_decimal(raw) -> Decimal | None:
    if raw is None:
        return None
    s = str(raw).replace(",", "").strip()
    if not s or s == "-":
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _normalise_side(raw) -> str | None:
    if not raw:
        return None
    s = str(raw).strip().upper()
    if s in {"BUY", "B"}:
        return "BUY"
    if s in {"SELL", "S"}:
        return "SELL"
    return None


def parse_dataframe(df: pd.DataFrame, kind: DealKind) -> list[DealRow]:
    """Pure parse — no I/O. Tolerates renamed columns and extra columns;
    raises only when the frame is missing the core fields we need."""
    if df is None or df.empty:
        return []

    cols = set(df.columns)
    missing = EXPECTED_COLS - cols
    if missing:
        raise DealsParseError(
            f"nselib {kind} deals frame missing columns: {missing}; got {sorted(cols)}"
        )

    # Use `to_dict("records")` so column names with `/` and `.`
    # (e.g. "Buy/Sell", "TradePrice/Wght.Avg.Price") survive intact.
    out: list[DealRow] = []
    for rec in df.to_dict(orient="records"):
        d = _parse_dd_mon_yyyy(rec.get("Date"))
        if d is None:
            continue
        symbol = (rec.get("Symbol") or "").strip().upper()
        if not symbol:
            continue
        side = _normalise_side(rec.get("Buy/Sell"))
        if side is None:
            continue
        qty = _parse_int(rec.get("QuantityTraded"))
        if qty is None or qty <= 0:
            continue
        price = _parse_decimal(rec.get("TradePrice/Wght.Avg.Price"))
        if price is None or price <= 0:
            continue

        remark_raw = rec.get("Remarks")
        remark = (
            None
            if remark_raw is None or str(remark_raw).strip() in {"", "-", "nan", "NaN"}
            else str(remark_raw).strip()
        )
        out.append(
            DealRow(
                trade_date=d,
                symbol=symbol,
                security_name=str(rec.get("SecurityName") or "").strip(),
                client_name=str(rec.get("ClientName") or "").strip(),
                side=side,
                quantity=qty,
                avg_price=price,
                remarks=remark,
                kind=kind,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Async fetch — runs nselib in a thread (it's sync internally)
# ---------------------------------------------------------------------------


def _sync_fetch(period: str, kind: DealKind) -> pd.DataFrame:
    # Lazy import — keep cold-start cheap if nselib isn't called.
    from nselib import capital_market as cm

    if kind == "bulk":
        return cm.bulk_deal_data(period=period)
    if kind == "block":
        return cm.block_deals_data(period=period)
    raise ValueError(f"unknown kind: {kind}")


async def fetch(
    *, kind: DealKind = "bulk", period: str = "1M", timeout_s: float = 60.0
) -> list[DealRow]:
    """Pull every deal NSE has on file for the given window across the
    full market (we filter to our universe at upsert time).

    period accepts nselib's string format: "1D", "1W", "1M", "3M", "6M", "1Y".
    """
    try:
        df = await asyncio.wait_for(
            asyncio.to_thread(_sync_fetch, period, kind), timeout=timeout_s
        )
    except asyncio.TimeoutError as e:
        raise DealsFetchError(f"nselib {kind} timeout after {timeout_s}s") from e
    except DealsParseError:
        raise
    except Exception as e:  # noqa: BLE001
        raise DealsFetchError(f"nselib {kind} error: {e!s}") from e

    return parse_dataframe(df, kind=kind)


# ---------------------------------------------------------------------------
# Helpers used by the API
# ---------------------------------------------------------------------------


def utc_close_of_trade_day(d: date) -> datetime:
    """End-of-day UTC for a trade date (matches `prices_daily.ts` convention)."""
    from datetime import timezone
    return datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc)
