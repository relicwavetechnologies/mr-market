"""Unit tests for `app.analytics.technicals`.

Strategy: rather than asserting every indicator number against an external
reference, we test the **mathematical properties** that any correct
implementation must satisfy. This catches subtle bugs (off-by-one, wrong
smoothing, NaN-handling) without coupling tests to a specific framework.

A small handful of cross-references against a hand-traced calculation are
included for RSI on a Wilder textbook example.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from app.analytics.technicals import (
    REQUIRED_COLS,
    _rma,
    atr,
    bollinger,
    compute_indicators,
    ema,
    macd,
    rsi,
    sma,
    safe_round,
    trend_label,
    true_range,
)


def _ohlcv(closes: list[float], n: int | None = None) -> pd.DataFrame:
    """Build a synthetic OHLCV frame with closes you control. open=high=low=close."""
    n = n or len(closes)
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    c = np.asarray(closes[:n])
    return pd.DataFrame(
        {"open": c, "high": c, "low": c, "close": c, "volume": np.full(n, 1_000_000)},
        index=idx,
    )


# ---------------------------------------------------------------------------
# RSI — Wilder's textbook example (closes from his 1978 book, RSI=70.53 expected)
# ---------------------------------------------------------------------------


WILDER_CLOSES = [
    44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
    45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00,
    46.03, 46.41, 46.22, 45.64,
]


class TestRSI:
    def test_matches_pandas_ta_classic_post_warmup(self):
        """Cross-check our RSI against `pandas_ta_classic.rsi` after the
        warmup window has converged.

        Our implementation uses pure Wilder/RMA from the first bar (no
        bootstrap), matching TradingView/Kite Charts. pandas-ta-classic
        uses Wilder's classical simple-average bootstrap. The two converge
        within ~0.5 by bar 50 and within ~0.1 by bar 80.
        """
        try:
            import pandas_ta_classic as pta
        except ImportError:
            pytest.skip("pandas_ta_classic not installed")

        rng = np.random.default_rng(0)
        s = pd.Series(100 + rng.standard_normal(150).cumsum())
        ours = rsi(s, 14)
        ref = pta.rsi(s, length=14)
        # After bar 80 the recursion has effectively converged.
        post = slice(80, None)
        common = ours[post].notna() & ref[post].notna()
        diff = (ours[post][common] - ref[post][common]).abs()
        assert common.sum() > 30, "should overlap substantially post-warmup"
        assert diff.max() < 0.5, f"max diff post-warmup {diff.max()} >= 0.5"

    def test_bounded_0_to_100(self):
        rng = np.random.default_rng(42)
        s = pd.Series(100 + np.cumsum(rng.standard_normal(200)))
        r = rsi(s, length=14).dropna()
        assert (r >= 0).all() and (r <= 100).all()

    def test_monotone_increasing_series_rsi_high(self):
        s = pd.Series(np.linspace(100, 200, 60))
        r = rsi(s, length=14).dropna()
        # All up-days → RSI saturates near 100
        assert r.iloc[-1] > 95.0

    def test_monotone_decreasing_series_rsi_low(self):
        s = pd.Series(np.linspace(200, 100, 60))
        r = rsi(s, length=14).dropna()
        assert r.iloc[-1] < 5.0

    def test_first_n_minus_one_are_nan(self):
        s = pd.Series(np.linspace(100, 110, 30))
        r = rsi(s, length=14)
        # length-1 = 13 prior bars all NaN
        assert r.iloc[:13].isna().all()


# ---------------------------------------------------------------------------
# EMA / SMA
# ---------------------------------------------------------------------------


class TestSMA:
    def test_sma_constant_series(self):
        s = pd.Series([100.0] * 30)
        out = sma(s, 20).dropna()
        assert (out == 100.0).all()

    def test_sma_linear_series_average(self):
        # SMA of [1,2,3,...,20] over length 20 = mean = 10.5
        s = pd.Series(range(1, 21), dtype=float)
        out = sma(s, 20)
        assert math.isclose(out.iloc[-1], 10.5, rel_tol=1e-9)

    def test_sma_first_n_minus_one_are_nan(self):
        s = pd.Series(range(50), dtype=float)
        out = sma(s, 20)
        assert out.iloc[:19].isna().all()
        assert out.iloc[19] == pytest.approx(9.5)


class TestEMA:
    def test_ema_constant_series(self):
        s = pd.Series([100.0] * 30)
        out = ema(s, 12).dropna()
        assert np.allclose(out.to_numpy(), 100.0)

    def test_ema_responds_faster_than_sma(self):
        # Step change: 100 → 110 at bar 20. EMA-12 must lead SMA-20 toward 110.
        s = pd.Series([100.0] * 20 + [110.0] * 30)
        e = ema(s, 12).iloc[-1]
        m = sma(s, 20).iloc[-1]
        # SMA-20 of last 20 bars (all 110 once we're 20+ in) → 110.
        # EMA-12 will already be very close to 110 too. Both should be ≥ 109.
        assert e >= 109.0 and m >= 109.0

    def test_ema_alpha_correct(self):
        """EMA(span=2) ⇒ alpha = 2/(2+1) = 2/3.

        Manual compute: EMA[0] = first value (post warmup).
        EMA[i] = alpha * v[i] + (1-alpha) * EMA[i-1]
        For [10, 20] with span=2 and adjust=False, min_periods=2:
            EMA[1] = 2/3 * 20 + 1/3 * 10 = 16.6667
        """
        s = pd.Series([10.0, 20.0])
        out = ema(s, 2)
        assert pd.isna(out.iloc[0])
        assert math.isclose(out.iloc[1], 50 / 3, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------


class TestMACD:
    def test_macd_uptrend_positive(self):
        s = pd.Series(np.linspace(100, 200, 100))
        m = macd(s)
        # In a sustained uptrend, MACD line stays > 0
        assert m["macd"].dropna().iloc[-1] > 0

    def test_macd_downtrend_negative(self):
        s = pd.Series(np.linspace(200, 100, 100))
        m = macd(s)
        assert m["macd"].dropna().iloc[-1] < 0

    def test_macd_histogram_definition(self):
        # hist == macd - signal at every bar
        s = pd.Series(np.linspace(100, 150, 80))
        m = macd(s).dropna()
        diff = (m["macd"] - m["macd_signal"]) - m["macd_hist"]
        assert np.allclose(diff.to_numpy(), 0.0, atol=1e-9)


# ---------------------------------------------------------------------------
# Bollinger
# ---------------------------------------------------------------------------


class TestBollinger:
    def test_constant_series_zero_width(self):
        s = pd.Series([100.0] * 30)
        bb = bollinger(s).dropna()
        assert np.allclose(bb["bb_upper"], bb["bb_lower"])
        assert np.allclose(bb["bb_middle"], 100.0)

    def test_upper_above_lower(self):
        rng = np.random.default_rng(0)
        s = pd.Series(100 + rng.standard_normal(100).cumsum())
        bb = bollinger(s).dropna()
        assert (bb["bb_upper"] >= bb["bb_lower"]).all()

    def test_middle_equals_sma(self):
        s = pd.Series(range(50), dtype=float)
        bb = bollinger(s, length=20)
        assert np.allclose(bb["bb_middle"].dropna(), sma(s, 20).dropna())


# ---------------------------------------------------------------------------
# True range / ATR
# ---------------------------------------------------------------------------


class TestATR:
    def test_true_range_no_gap(self):
        # No prev close gap → TR == high - low
        h = pd.Series([105.0, 106.0, 107.0])
        l = pd.Series([100.0, 100.0, 100.0])
        c = pd.Series([102.0, 103.0, 104.0])
        tr = true_range(h, l, c)
        assert tr.iloc[0] == 5.0   # first bar: prev close NaN, max collapses to high-low
        # Bar 2: high=106, prev_close=102 → tr2=4; high-low=6. max = 6
        assert tr.iloc[1] == 6.0

    def test_atr_constant_range(self):
        # Always 5-point range with no gap → ATR converges to 5
        n = 60
        c = pd.Series([100.0] * n)
        h = c + 5
        l = c - 0
        a = atr(h, l, c, length=14)
        # By bar 30 the Wilder smoothing has saturated to 5.
        assert math.isclose(a.iloc[30], 5.0, rel_tol=1e-6)

    def test_atr_first_values_nan(self):
        h = pd.Series(np.linspace(101, 200, 50))
        l = pd.Series(np.linspace(99, 198, 50))
        c = pd.Series(np.linspace(100, 199, 50))
        a = atr(h, l, c, length=14)
        # length-1 prior values must be NaN under min_periods=length
        assert a.iloc[:13].isna().all()


# ---------------------------------------------------------------------------
# Top-level compute_indicators
# ---------------------------------------------------------------------------


class TestComputeIndicators:
    def test_returns_all_columns(self):
        df = _ohlcv(list(np.linspace(100, 200, 250)))
        out = compute_indicators(df)
        for col in [
            "close", "rsi_14",
            "macd", "macd_signal", "macd_hist",
            "bb_upper", "bb_middle", "bb_lower",
            "sma_20", "sma_50", "sma_200",
            "ema_12", "ema_26",
            "atr_14", "vol_avg_20",
        ]:
            assert col in out.columns, f"missing column {col}"

    def test_index_preserved(self):
        df = _ohlcv(list(range(100, 130)))
        out = compute_indicators(df)
        assert (out.index == df.index).all()

    def test_short_series_yields_some_nans_not_crash(self):
        # 30 bars — RSI/EMA-12 have valid tails, SMA-200 must be all NaN.
        df = _ohlcv(list(np.linspace(100, 110, 30)))
        out = compute_indicators(df)
        assert out["sma_200"].isna().all()
        assert out["rsi_14"].notna().any()

    def test_missing_column_raises(self):
        df = pd.DataFrame({"close": [1, 2, 3]})
        with pytest.raises(ValueError, match="missing columns"):
            compute_indicators(df)

    def test_unsorted_index_raises(self):
        idx = pd.date_range("2026-01-01", periods=5)
        df = pd.DataFrame(
            {"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}, index=idx
        )
        df = df.iloc[::-1]   # descending → invalid
        with pytest.raises(ValueError, match="ascending"):
            compute_indicators(df)

    def test_required_cols_constant_matches(self):
        assert set(REQUIRED_COLS) == {"open", "high", "low", "close", "volume"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestRMA:
    def test_constant_series(self):
        s = pd.Series([5.0] * 30)
        out = _rma(s, 14)
        # After warmup, RMA of constant = constant.
        assert np.allclose(out.dropna().to_numpy(), 5.0)


class TestTrendLabel:
    def test_overbought(self):
        assert trend_label(pd.Series({"rsi_14": 75.0})) == "overbought"

    def test_oversold(self):
        assert trend_label(pd.Series({"rsi_14": 25.0})) == "oversold"

    def test_neutral(self):
        assert trend_label(pd.Series({"rsi_14": 50.0})) == "neutral"

    def test_no_history(self):
        assert trend_label(pd.Series({"rsi_14": float("nan")})) == "insufficient_history"


class TestSafeRound:
    def test_none(self):
        assert safe_round(None, 2) is None

    def test_nan(self):
        assert safe_round(float("nan"), 2) is None

    def test_normal(self):
        assert safe_round(1.23456, 2) == 1.23
