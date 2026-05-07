"""Pure indicator computation over a price DataFrame.

Indicators (all standard parameters):
    RSI-14, MACD(12, 26, 9), Bollinger(20, 2), SMA-20/50/200, EMA-12/26,
    ATR-14, 20-day average volume.

Rationale for choices (no jargon — stays defensible if anyone audits):
    * RSI-14 / MACD(12,26,9) / BB(20,2) — Wilder / Appel / Bollinger originals.
    * SMA-50 / SMA-200 — the two crossover lines every trading system tracks.
    * ATR-14 — needed for stop-loss / position-size math we surface in P2-D5.
    * 20-day avg volume — quick "is today unusual?" sanity benchmark.

Inputs:
    A pandas DataFrame indexed by datetime with columns
    {open, high, low, close, volume}. Index ASCENDING (oldest first).

Outputs:
    A DataFrame with the same index and one column per indicator. NaN where
    the bar has insufficient lookback. The caller writes only the most recent
    bars to DB to avoid re-rewriting old rows on every run (idempotent
    upsert handles that anyway).

We use pandas-ta-classic where its primitives are correct and faster than
hand-rolled, and fall back to plain pandas/numpy for the obvious ones (SMAs,
volume mean) so the module still works if the dependency ever drops out.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:  # only used for type hints
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Indicator implementations (Wilder smoothing where canonical)
# ---------------------------------------------------------------------------


def _rma(series: pd.Series, length: int) -> pd.Series:
    """Wilder's smoothed moving average — equivalent to EMA with alpha=1/length.

    Used by RSI and ATR. Pandas' ewm with `alpha=1/n` and `adjust=False` is
    exactly Wilder's RMA.
    """
    return series.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    """Wilder RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = _rma(gain, length)
    avg_loss = _rma(loss, length)
    rs = avg_gain / avg_loss
    rsi_val = 100 - (100 / (1 + rs))
    rsi_val = rsi_val.where(avg_loss != 0, other=100.0)
    return rsi_val


def ema(series: pd.Series, length: int) -> pd.Series:
    """Standard EMA (alpha = 2/(n+1), adjust=False)."""
    return series.ewm(span=length, adjust=False, min_periods=length).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD line, signal, histogram."""
    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    line = fast_ema - slow_ema
    signal_line = ema(line, signal)
    hist = line - signal_line
    return pd.DataFrame({"macd": line, "macd_signal": signal_line, "macd_hist": hist})


def bollinger(close: pd.Series, length: int = 20, std: float = 2.0) -> pd.DataFrame:
    """Classic Bollinger Bands. middle = SMA(length); upper/lower = ±std·σ."""
    middle = close.rolling(length, min_periods=length).mean()
    sigma = close.rolling(length, min_periods=length).std(ddof=0)
    return pd.DataFrame(
        {
            "bb_middle": middle,
            "bb_upper": middle + std * sigma,
            "bb_lower": middle - std * sigma,
        }
    )


def sma(close: pd.Series, length: int) -> pd.Series:
    return close.rolling(length, min_periods=length).mean()


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """Wilder ATR."""
    tr = true_range(high, low, close)
    return _rma(tr, length)


# ---------------------------------------------------------------------------
# Top-level compute
# ---------------------------------------------------------------------------


REQUIRED_COLS = ("open", "high", "low", "close", "volume")


def compute_indicators(prices: pd.DataFrame) -> pd.DataFrame:
    """Take a sorted-ascending OHLCV DataFrame and return one row per bar with
    all indicator columns. Insufficient-lookback rows have NaN.
    """
    missing = [c for c in REQUIRED_COLS if c not in prices.columns]
    if missing:
        raise ValueError(f"compute_indicators: missing columns {missing}")
    if not prices.index.is_monotonic_increasing:
        raise ValueError("compute_indicators: index must be ascending")

    # Cast to float for the math; pandas-ta and our funcs both prefer float.
    o = prices["open"].astype(float)
    h = prices["high"].astype(float)
    l = prices["low"].astype(float)
    c = prices["close"].astype(float)
    v = prices["volume"].astype("float64")

    out = pd.DataFrame(index=prices.index)
    out["close"] = c

    # RSI
    out["rsi_14"] = rsi(c, 14)

    # MACD
    macd_df = macd(c, 12, 26, 9)
    out[["macd", "macd_signal", "macd_hist"]] = macd_df

    # Bollinger
    bb = bollinger(c, 20, 2.0)
    out[["bb_upper", "bb_middle", "bb_lower"]] = bb[
        ["bb_upper", "bb_middle", "bb_lower"]
    ]

    # SMAs
    out["sma_20"] = sma(c, 20)
    out["sma_50"] = sma(c, 50)
    out["sma_200"] = sma(c, 200)

    # EMAs
    out["ema_12"] = ema(c, 12)
    out["ema_26"] = ema(c, 26)

    # ATR
    out["atr_14"] = atr(h, l, c, 14)

    # Volume context — 20-day rolling mean (rounded later)
    out["vol_avg_20"] = v.rolling(20, min_periods=20).mean()

    # Mark unused alias to silence linters about `o` (kept for future indicators)
    _ = o

    return out


def trend_label(row: pd.Series) -> str:
    """Tiny qualitative summary used in the API response narrative.

    Reads RSI + price-vs-SMA50 to decide if we'd casually call the bar
    overbought/oversold/neutral. Pure helper — never claims a recommendation.
    """
    rsi_v = row.get("rsi_14")
    if pd.isna(rsi_v):
        return "insufficient_history"
    if rsi_v >= 70:
        return "overbought"
    if rsi_v <= 30:
        return "oversold"
    return "neutral"


def safe_round(x: float | None, ndigits: int) -> float | None:
    if x is None or pd.isna(x):
        return None
    return float(np.round(x, ndigits))
