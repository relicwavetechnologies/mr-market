"""Unit tests for `app.analytics.levels` — pure functions only."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app.analytics.levels import (
    FIB_RATIOS,
    Pivots,
    classic_pivots,
    compute_levels,
    fibonacci_levels,
    find_sr_levels,
)


# ---------------------------------------------------------------------------
# 1. Pivots
# ---------------------------------------------------------------------------


class TestClassicPivots:
    def test_textbook_values(self):
        # H=110, L=90, C=100. PP = (110+90+100)/3 = 100.
        # R1 = 2*100 - 90 = 110.   S1 = 2*100 - 110 = 90.
        # R2 = 100 + 20 = 120.     S2 = 100 - 20 = 80.
        # R3 = 110 + 2*(100-90) = 130.  S3 = 90 - 2*(110-100) = 70.
        p = classic_pivots(Decimal("110"), Decimal("90"), Decimal("100"))
        assert p.pp == Decimal("100.0000")
        assert p.r1 == Decimal("110.0000")
        assert p.s1 == Decimal("90.0000")
        assert p.r2 == Decimal("120.0000")
        assert p.s2 == Decimal("80.0000")
        assert p.r3 == Decimal("130.0000")
        assert p.s3 == Decimal("70.0000")

    def test_returns_pivots_dataclass(self):
        p = classic_pivots(Decimal("100"), Decimal("90"), Decimal("95"))
        assert isinstance(p, Pivots)

    def test_orderings(self):
        """S3 < S2 < S1 < PP < R1 < R2 < R3 always."""
        p = classic_pivots(Decimal("110"), Decimal("90"), Decimal("100"))
        assert p.s3 < p.s2 < p.s1 < p.pp < p.r1 < p.r2 < p.r3

    def test_decimal_precision(self):
        # 100.123, 99.456, 99.789 — not round numbers
        p = classic_pivots(
            Decimal("100.123"), Decimal("99.456"), Decimal("99.789")
        )
        # PP = sum/3 = 99.78933... → round to 4dp = 99.7893
        assert p.pp == Decimal("99.7893")

    def test_decimal_input_required(self):
        # int/float input via Decimal string still works
        p = classic_pivots(Decimal("100"), Decimal("80"), Decimal("90"))
        assert p.pp == Decimal("90.0000")


# ---------------------------------------------------------------------------
# 2. Multi-touch S/R
# ---------------------------------------------------------------------------


def _make_df(closes_highs_lows: list[tuple[float, float, float]]) -> pd.DataFrame:
    """Build a DataFrame of (close, high, low) tuples indexed by sequential dates."""
    n = len(closes_highs_lows)
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    rows = []
    for c, h, l in closes_highs_lows:
        rows.append({"open": c, "high": h, "low": l, "close": c, "volume": 1_000_000})
    return pd.DataFrame(rows, index=idx)


class TestSRLevels:
    def test_empty_df(self):
        above, below = find_sr_levels(pd.DataFrame())
        assert above == [] and below == []

    def test_below_min_touches_returns_empty(self):
        # 3 bars, each unique price → no level reaches min_touches=3
        df = _make_df([
            (100, 102, 98),
            (105, 107, 103),
            (110, 112, 108),
        ])
        above, below = find_sr_levels(df, window=10, min_touches=3)
        # Each bin gets ≤2 touches (high+low for one bar). Should be empty.
        assert above == [] and below == []

    def test_repeated_high_clusters_into_resistance(self):
        # Build 5 bars with the same ~150 high level repeatedly hit.
        bars = [
            (140.0, 150.0, 138.0),  # day 1
            (142.0, 150.1, 140.0),  # day 2 — re-touches 150
            (143.0, 149.9, 141.0),  # day 3 — re-touches ~150
            (141.0, 150.05, 140.5), # day 4
            (139.0, 150.0, 138.0),  # day 5
        ]
        # Latest close is 139 → 150 should be ABOVE close = resistance.
        df = _make_df(bars)
        above, below = find_sr_levels(df, window=10, bin_pct=0.5, min_touches=3)
        # The 150 cluster should be a single resistance level with >=3 touches.
        assert any(149 <= float(l.price) <= 151 for l in above)
        # No prominent support cluster expected.

    def test_repeated_low_clusters_into_support(self):
        bars = [
            (110.0, 115.0, 100.0),
            (108.0, 113.0, 99.95),
            (107.0, 112.0, 100.05),
            (109.0, 114.0, 100.0),
            (115.0, 116.0, 100.1),  # close 115, latest
        ]
        df = _make_df(bars)
        above, below = find_sr_levels(df, window=10, bin_pct=0.5, min_touches=3)
        # 100 cluster should be SUPPORT below latest close 115.
        assert any(99 <= float(l.price) <= 101 for l in below)

    def test_top_k_cap(self):
        # Many distinct levels, all hit 3 times each.
        bars = []
        prices = [100, 110, 120, 130, 140, 150, 160, 170, 180]
        for p in prices:
            for _ in range(3):
                bars.append((50.0, float(p), float(p) - 0.05))   # high cluster
        df = _make_df(bars)
        above, below = find_sr_levels(df, window=200, bin_pct=0.5, min_touches=3, top_k=5)
        assert len(above) <= 5

    def test_pct_from_close_sign(self):
        bars = [(100.0, 100.5, 99.5)] * 5
        df = _make_df(bars + [(100.0, 100.0, 99.0), (100.0, 100.0, 99.0), (100.0, 100.0, 99.0)])
        above, below = find_sr_levels(df, window=20, bin_pct=0.5, min_touches=3)
        # Above-close levels must have positive pct_from_close
        for l in above:
            assert float(l.pct_from_close) > 0
        for l in below:
            assert float(l.pct_from_close) < 0

    def test_records_last_touch(self):
        # Same level on day 1 and day 5 — last_touch should be day 5
        bars = [
            (100.0, 105.0, 95.0),  # day 1, high 105
            (100.0, 102.0, 95.0),
            (100.0, 102.0, 95.0),
            (100.0, 102.0, 95.0),
            (100.0, 105.05, 95.0), # day 5, re-touches 105
            (100.0, 105.0, 95.0),  # day 6
            (100.0, 102.0, 95.0),
        ]
        df = _make_df(bars)
        above, _below = find_sr_levels(df, window=10, bin_pct=0.5, min_touches=3)
        # Find the 105 cluster
        cluster = next((l for l in above if 104 <= float(l.price) <= 106), None)
        assert cluster is not None
        # Last touch should be the most recent date in the dataset that touched 105
        all_dates = list(df.index)
        # Bars 0, 4, 5 hit ~105. Last is bar 5 → all_dates[5]
        assert cluster.last_touch == all_dates[5].date()


# ---------------------------------------------------------------------------
# 3. Fibonacci retracements
# ---------------------------------------------------------------------------


class TestFibonacci:
    def test_uptrend(self):
        # Linear up from 100 to 200 over 50 days. Latest close ≈ 200 → "up".
        n = 50
        closes = list(np.linspace(100, 200, n))
        df = _make_df([(c, c + 1, c - 1) for c in closes])
        fibs = fibonacci_levels(df, window=n)
        assert fibs is not None
        assert fibs.direction == "up"
        # Highest high should be 201 (200+1), lowest low 99 (100-1)
        assert float(fibs.swing_high) == pytest.approx(201.0, rel=1e-6)
        assert float(fibs.swing_low) == pytest.approx(99.0, rel=1e-6)
        # Range: 102. 50% retrace from high = 201 - 102*0.5 = 150
        assert float(fibs.retraces["0.500"]) == pytest.approx(150.0, abs=0.01)

    def test_downtrend(self):
        n = 50
        closes = list(np.linspace(200, 100, n))
        df = _make_df([(c, c + 1, c - 1) for c in closes])
        fibs = fibonacci_levels(df, window=n)
        assert fibs is not None
        assert fibs.direction == "down"
        # 50% retrace from low = 99 + 102*0.5 = 150
        assert float(fibs.retraces["0.500"]) == pytest.approx(150.0, abs=0.01)

    def test_all_standard_ratios_present(self):
        df = _make_df([(100 + i, 100 + i + 1, 100 + i - 1) for i in range(50)])
        fibs = fibonacci_levels(df, window=50)
        assert fibs is not None
        for r in FIB_RATIOS:
            assert str(r) in fibs.retraces

    def test_flat_or_constant_returns_none(self):
        # Constant price → swing_high == swing_low → None
        df = _make_df([(100.0, 100.0, 100.0)] * 50)
        fibs = fibonacci_levels(df, window=50)
        assert fibs is None

    def test_empty_returns_none(self):
        assert fibonacci_levels(pd.DataFrame()) is None

    def test_uses_lookback_window(self):
        # If we ask for window=20, we only see the last 20 bars.
        n = 100
        closes = [100.0] * 80 + list(np.linspace(100, 200, 20))
        df = _make_df([(c, c + 1, c - 1) for c in closes])
        fibs = fibonacci_levels(df, window=20)
        assert fibs is not None
        # Swing low within last 20 bars ≈ 99 (100-1), high ≈ 201 (200+1)
        assert float(fibs.swing_high) == pytest.approx(201.0, abs=0.01)


# ---------------------------------------------------------------------------
# 4. Top-level compute_levels
# ---------------------------------------------------------------------------


class TestComputeLevels:
    def test_empty_df(self):
        out = compute_levels(pd.DataFrame())
        assert out == {"available": False, "reason": "no prices"}

    def test_single_bar_insufficient(self):
        df = _make_df([(100.0, 102.0, 98.0)])
        out = compute_levels(df)
        assert out["available"] is False

    def test_returns_full_payload(self):
        n = 100
        rng = np.random.default_rng(0)
        closes = 100 + rng.standard_normal(n).cumsum()
        df = _make_df([(c, c + 1, c - 1) for c in closes])
        out = compute_levels(df, window=90)
        assert out["available"] is True
        assert "pivots" in out
        assert {"pp", "r1", "r2", "r3", "s1", "s2", "s3"} <= set(out["pivots"].keys())
        assert "support" in out and "resistance" in out
        assert "fibonacci" in out
        assert out["lookback_bars"] <= 90
        # `as_of_close` must be a number that round-trips through json.dumps
        import json
        assert isinstance(out["as_of_close"], float)
        json.dumps(out)   # no exception → JSON-serialisable
