"""Support / resistance levels from EOD bars.

Three independent computations, all pure functions:

  1. **Classic floor-trader pivots** from the previous trading day's HLC.
       PP = (H+L+C) / 3
       R1 = 2·PP − L      |  S1 = 2·PP − H
       R2 = PP + (H−L)    |  S2 = PP − (H−L)
       R3 = H + 2·(PP−L)  |  S3 = L − 2·(H−PP)

  2. **Multi-touch S/R** — bucketise every high and every low across the
     lookback window into 0.5%-of-current-price bins, count "touches" per
     bin, return the top-K above (resistance candidates) and top-K below
     (support candidates) the latest close. Each level has a touch count
     plus the most-recent touch date so the caller can grade staleness.

  3. **Fibonacci retracements** — pick the highest high and lowest low in
     the lookback window; if the latest close sits closer to the high the
     trend is up and we project retraces *below* the high; if closer to the
     low we project retraces *above* the low.

We never persist these — they're derivative of `prices_daily`, recompute fast
(<10 ms for 90 bars), and would need invalidation on every nightly ingest.
The endpoint computes on-demand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

# Standard fib retraces (Elliott / classic).
FIB_RATIOS = (Decimal("0.236"), Decimal("0.382"), Decimal("0.500"), Decimal("0.618"), Decimal("0.786"))


# ---------------------------------------------------------------------------
# 1. Pivots
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Pivots:
    pp: Decimal
    r1: Decimal
    r2: Decimal
    r3: Decimal
    s1: Decimal
    s2: Decimal
    s3: Decimal


def classic_pivots(high: Decimal, low: Decimal, close: Decimal) -> Pivots:
    """Floor-trader pivots from one prior-period HLC."""
    pp = (high + low + close) / Decimal(3)
    r1 = 2 * pp - low
    s1 = 2 * pp - high
    r2 = pp + (high - low)
    s2 = pp - (high - low)
    r3 = high + 2 * (pp - low)
    s3 = low - 2 * (high - pp)
    return Pivots(
        pp=_q(pp), r1=_q(r1), r2=_q(r2), r3=_q(r3),
        s1=_q(s1), s2=_q(s2), s3=_q(s3),
    )


def _q(d: Decimal) -> Decimal:
    """Round to 4 decimal places — matches our DB schema for prices."""
    return d.quantize(Decimal("0.0001"))


# ---------------------------------------------------------------------------
# 2. Multi-touch support / resistance
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TouchedLevel:
    price: Decimal
    touches: int
    last_touch: date
    pct_from_close: Decimal


def find_sr_levels(
    prices: pd.DataFrame,
    *,
    window: int = 90,
    bin_pct: float = 0.5,         # bin width as % of latest close
    min_touches: int = 3,
    top_k: int = 5,
) -> tuple[list[TouchedLevel], list[TouchedLevel]]:
    """Return (resistance_above_close, support_below_close) levels.

    Algorithm:
      * Take the last ``window`` bars (sorted ascending).
      * Bin every high and every low to a grid of width ``bin_pct`` % of
        the latest close. Round each price to its bin center.
      * Count occurrences per bin. Bins with ``< min_touches`` are dropped.
      * Split into above-close (resistance) and below-close (support).
      * Sort each side by touches desc, then by recency desc; cap to top_k.
    """
    if prices is None or prices.empty:
        return [], []

    df = prices.tail(window).copy()
    if df.empty:
        return [], []

    last_close = float(df["close"].iloc[-1])
    if last_close <= 0:
        return [], []

    bin_width = last_close * bin_pct / 100.0
    if bin_width <= 0:
        return [], []

    # Build (price, when) pairs from highs and lows.
    pairs: list[tuple[float, date]] = []
    for ts, row in df.iterrows():
        d = ts.date() if hasattr(ts, "date") else ts
        for col in ("high", "low"):
            v = float(row[col])
            if v > 0:
                pairs.append((v, d))

    if not pairs:
        return [], []

    # Bin → list of dates; cluster center is the bin midpoint.
    counts: dict[int, list[date]] = {}
    for price, d in pairs:
        idx = int(round(price / bin_width))
        counts.setdefault(idx, []).append(d)

    rows: list[TouchedLevel] = []
    for idx, dates in counts.items():
        if len(dates) < min_touches:
            continue
        center = idx * bin_width
        rows.append(
            TouchedLevel(
                price=Decimal(str(round(center, 4))),
                touches=len(dates),
                last_touch=max(dates),
                pct_from_close=Decimal(str(round((center - last_close) / last_close * 100, 4))),
            )
        )

    above = sorted(
        [r for r in rows if r.price > Decimal(str(last_close))],
        key=lambda r: (-r.touches, -r.last_touch.toordinal()),
    )[:top_k]
    below = sorted(
        [r for r in rows if r.price < Decimal(str(last_close))],
        key=lambda r: (-r.touches, -r.last_touch.toordinal()),
    )[:top_k]

    return above, below


# ---------------------------------------------------------------------------
# 3. Fibonacci retracements
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FibLevels:
    direction: str        # "up" | "down" | "flat"
    swing_high: Decimal
    swing_low: Decimal
    swing_high_date: date
    swing_low_date: date
    range_: Decimal
    retraces: dict[str, Decimal] = field(default_factory=dict)  # "0.236" -> price


def fibonacci_levels(prices: pd.DataFrame, *, window: int = 60) -> FibLevels | None:
    """Pick swing high / swing low in the lookback window; project the standard
    fib retraces toward the latest close.
    """
    if prices is None or prices.empty:
        return None

    df = prices.tail(window).copy()
    if df.empty:
        return None

    high_idx = df["high"].idxmax()
    low_idx = df["low"].idxmin()
    swing_high = Decimal(str(round(float(df.loc[high_idx, "high"]), 4)))
    swing_low = Decimal(str(round(float(df.loc[low_idx, "low"]), 4)))
    if swing_high <= swing_low:
        return None

    last_close = Decimal(str(round(float(df["close"].iloc[-1]), 4)))
    range_ = swing_high - swing_low
    midpoint = swing_low + range_ / 2

    if last_close >= midpoint:
        direction = "up"
        retraces = {
            str(r): _q(swing_high - range_ * r) for r in FIB_RATIOS
        }
    else:
        direction = "down"
        retraces = {
            str(r): _q(swing_low + range_ * r) for r in FIB_RATIOS
        }

    return FibLevels(
        direction=direction,
        swing_high=swing_high,
        swing_low=swing_low,
        swing_high_date=high_idx.date() if hasattr(high_idx, "date") else high_idx,
        swing_low_date=low_idx.date() if hasattr(low_idx, "date") else low_idx,
        range_=_q(range_),
        retraces=retraces,
    )


# ---------------------------------------------------------------------------
# Top-level convenience
# ---------------------------------------------------------------------------


def compute_levels(prices: pd.DataFrame, *, window: int = 90) -> dict:
    """One-shot computation used by the API + LLM tool. Returns a JSON-friendly
    dict with pivots / multi-touch S/R / fibs / a small diagnostic.
    """
    if prices is None or prices.empty:
        return {"available": False, "reason": "no prices"}

    df = prices.sort_index()
    if len(df) < 2:
        return {"available": False, "reason": "need >=2 bars"}

    # Pivots from the prior trading day.
    prior = df.iloc[-2]
    p = classic_pivots(
        Decimal(str(prior["high"])),
        Decimal(str(prior["low"])),
        Decimal(str(prior["close"])),
    )

    above, below = find_sr_levels(df, window=window)
    fibs = fibonacci_levels(df, window=min(window, 60))

    last_bar = df.iloc[-1]
    out = {
        "available": True,
        "as_of_close": float(last_bar["close"]),
        "as_of_date": (df.index[-1].date().isoformat()
                       if hasattr(df.index[-1], "date") else None),
        "pivots": {
            "pp": str(p.pp), "r1": str(p.r1), "r2": str(p.r2), "r3": str(p.r3),
            "s1": str(p.s1), "s2": str(p.s2), "s3": str(p.s3),
        },
        "resistance": [
            {
                "price": str(r.price),
                "touches": r.touches,
                "last_touch": r.last_touch.isoformat(),
                "pct_from_close": str(r.pct_from_close),
            }
            for r in above
        ],
        "support": [
            {
                "price": str(r.price),
                "touches": r.touches,
                "last_touch": r.last_touch.isoformat(),
                "pct_from_close": str(r.pct_from_close),
            }
            for r in below
        ],
        "fibonacci": (
            {
                "direction": fibs.direction,
                "swing_high": str(fibs.swing_high),
                "swing_high_date": fibs.swing_high_date.isoformat(),
                "swing_low": str(fibs.swing_low),
                "swing_low_date": fibs.swing_low_date.isoformat(),
                "range": str(fibs.range_),
                "retraces": {k: str(v) for k, v in fibs.retraces.items()},
            }
            if fibs is not None
            else None
        ),
        "lookback_bars": int(min(window, len(df))),
    }
    return out


# Convenience for tests / manual checks.
def _ohlc_df_from_pairs(*pairs) -> pd.DataFrame:
    """Helper to build a tiny OHLCV frame from (date, open, high, low, close, vol)."""
    idx = [pd.Timestamp(d) for d, *_ in pairs]
    rows = [
        {"open": o, "high": h, "low": l, "close": c, "volume": v}
        for _, o, h, l, c, v in pairs
    ]
    df = pd.DataFrame(rows, index=idx).sort_index()
    return df


def _safe_float(x) -> float | None:
    if x is None or pd.isna(x):
        return None
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    if isinstance(x, Decimal):
        return float(x)
    return None
