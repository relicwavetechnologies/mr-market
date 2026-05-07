"""Unit tests for the triangulation engine — pure functions, no I/O."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.data.triangulate import (
    HIGH_THRESHOLD,
    MED_THRESHOLD,
    _classify,
    _decimal_median,
    _max_pairwise_spread,
    triangulate,
)
from app.data.types import Confidence, Quote


def _q(price: str, source: str = "yfinance") -> Quote:
    return Quote(
        ticker="TEST",
        price=Decimal(price),
        source=source,  # type: ignore[arg-type]
        fetched_at=datetime.now(timezone.utc),
    )


# --- _max_pairwise_spread ---------------------------------------------------

class TestSpread:
    def test_empty(self):
        assert _max_pairwise_spread([]) == Decimal(0)

    def test_single(self):
        assert _max_pairwise_spread([Decimal("100")]) == Decimal(0)

    def test_equal(self):
        assert _max_pairwise_spread([Decimal("100"), Decimal("100")]) == Decimal(0)

    def test_small_spread(self):
        # 100.00 vs 100.05 → 0.05%
        s = _max_pairwise_spread([Decimal("100"), Decimal("100.05")])
        assert s == Decimal("0.0005")

    def test_wide_spread(self):
        s = _max_pairwise_spread([Decimal("100"), Decimal("110")])
        assert s == Decimal("0.1")

    def test_uses_max_minus_min_not_first_pair(self):
        # 100, 100.01, 110 → spread is (110-100)/100 = 0.1
        s = _max_pairwise_spread(
            [Decimal("100"), Decimal("100.01"), Decimal("110")]
        )
        assert s == Decimal("0.1")


# --- _classify --------------------------------------------------------------

class TestClassify:
    def test_three_tight_is_high(self):
        assert _classify(3, Decimal("0.0005")) == Confidence.HIGH

    def test_three_at_threshold_is_high(self):
        assert _classify(3, HIGH_THRESHOLD) == Confidence.HIGH

    def test_three_just_over_high_is_med(self):
        assert _classify(3, HIGH_THRESHOLD + Decimal("0.00001")) == Confidence.MED

    def test_two_tight_is_med(self):
        assert _classify(2, Decimal("0.001")) == Confidence.MED

    def test_two_at_med_threshold_is_med(self):
        assert _classify(2, MED_THRESHOLD) == Confidence.MED

    def test_two_over_med_is_low(self):
        assert _classify(2, MED_THRESHOLD + Decimal("0.0001")) == Confidence.LOW

    def test_one_is_low(self):
        assert _classify(1, Decimal(0)) == Confidence.LOW

    def test_zero_is_low(self):
        assert _classify(0, Decimal(0)) == Confidence.LOW


# --- _decimal_median --------------------------------------------------------

class TestMedian:
    def test_one(self):
        assert _decimal_median([Decimal("100")]) == Decimal("100")

    def test_two_averaged(self):
        assert _decimal_median([Decimal("100"), Decimal("102")]) == Decimal("101")

    def test_three_middle(self):
        assert _decimal_median(
            [Decimal("100"), Decimal("101"), Decimal("110")]
        ) == Decimal("101")

    def test_four_averaged(self):
        assert _decimal_median(
            [Decimal("100"), Decimal("101"), Decimal("103"), Decimal("110")]
        ) == Decimal("102")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            _decimal_median([])


# --- triangulate (integration of the above) --------------------------------

class TestTriangulate:
    def test_four_tight_sources_high(self):
        qs = [
            _q("1436.20", "yfinance"),
            _q("1435.50", "nselib"),
            _q("1436.00", "screener"),
            _q("1436.20", "moneycontrol"),
        ]
        r = triangulate(qs, {}, "RELIANCE")
        assert r.confidence == Confidence.HIGH
        assert r.price == Decimal("1436.10")
        assert r.spread_pct < Decimal("0.1")  # 0.05% range
        assert len(r.sources) == 4
        assert r.failed_sources == {}
        assert r.note is None

    def test_two_close_sources_med(self):
        qs = [_q("100"), _q("100.3", "nselib")]
        r = triangulate(qs, {}, "X")
        assert r.confidence == Confidence.MED
        assert r.price == Decimal("100.15")

    def test_two_far_apart_low(self):
        qs = [_q("100"), _q("105", "nselib")]
        r = triangulate(qs, {}, "X")
        assert r.confidence == Confidence.LOW
        assert r.price is None
        assert "spread" in (r.note or "").lower()

    def test_one_source_low(self):
        qs = [_q("100")]
        r = triangulate(qs, {"nselib": "blocked"}, "X")
        assert r.confidence == Confidence.LOW
        assert r.price is None
        assert r.failed_sources == {"nselib": "blocked"}

    def test_zero_sources_low(self):
        r = triangulate([], {"yfinance": "timeout", "nselib": "403"}, "X")
        assert r.confidence == Confidence.LOW
        assert r.price is None
        assert r.note is not None
        assert "valid source" in r.note.lower()
        assert r.failed_sources == {"yfinance": "timeout", "nselib": "403"}

    def test_three_sources_one_outlier_low(self):
        # 100, 100.5, 105 → spread 5% — wider than MED, so LOW
        qs = [_q("100"), _q("100.5", "nselib"), _q("105", "screener")]
        r = triangulate(qs, {}, "X")
        assert r.confidence == Confidence.LOW
        assert r.price is None

    def test_to_dict_serialisable(self):
        import json

        qs = [_q("100"), _q("100.05", "nselib")]
        r = triangulate(qs, {"screener": "404"}, "X")
        # Should round-trip through json without error.
        s = json.dumps(r.to_dict())
        d = json.loads(s)
        assert d["confidence"] == "MED"
        assert d["ticker"] == "X"
        assert d["failed_sources"] == {"screener": "404"}
        assert len(d["sources"]) == 2
