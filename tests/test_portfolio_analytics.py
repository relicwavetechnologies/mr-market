"""Unit tests for portfolio diagnostics (P3-A5).

Pure-functional `compute_diagnostics` — no DB, no scrape. Hand-built
position lists + small helper maps cover every diagnostic field across
typical and edge-case portfolios.

Live integration of the API endpoint lives in
`tests/test_portfolio_diagnostics_api.py`.
"""

from __future__ import annotations

from decimal import Decimal

from app.analytics.portfolio import (
    Position,
    _drawdown_1y,
    _herfindahl,
    _safe_div,
    _top_n_pct,
    compute_diagnostics,
)


def D(s: str | int | float) -> Decimal:
    return Decimal(str(s))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestSafeDiv:
    def test_divides_normally(self):
        assert _safe_div(D("10"), D("4")) == D("2.5")

    def test_zero_denom_returns_zero(self):
        assert _safe_div(D("10"), D("0")) == D("0")


class TestHerfindahl:
    def test_single_position_is_one(self):
        # A 100% position → HHI = 1.0.
        assert _herfindahl([D("1.0")]) == D("1.00")

    def test_uniform_portfolio_is_inverse_n(self):
        # 10 equal positions → 10 × (0.1)² = 0.10.
        weights = [D("0.1")] * 10
        assert _herfindahl(weights) == D("0.10")

    def test_empty_returns_zero(self):
        assert _herfindahl([]) == D("0")


class TestTopNPct:
    def test_top_5_of_concentrated(self):
        # 6 positions, top 5 sum is 95% → result is 95.
        weights = [D("0.4"), D("0.3"), D("0.15"), D("0.05"), D("0.05"), D("0.05")]
        assert _top_n_pct(weights, 5) == D("95.0")

    def test_top_5_when_fewer_positions(self):
        # 3 positions; top 5 collapses to all of them.
        weights = [D("0.5"), D("0.3"), D("0.2")]
        assert _top_n_pct(weights, 5) == D("100.0")

    def test_empty_returns_zero(self):
        assert _top_n_pct([], 5) == D("0")


# ---------------------------------------------------------------------------
# compute_diagnostics — happy path
# ---------------------------------------------------------------------------


class TestCompute:
    def _two_position_portfolio(self) -> list[Position]:
        return [
            Position("RELIANCE", quantity=100, avg_price=D("1280"), current_price=D("1436")),
            Position("TCS", quantity=50, avg_price=D("2150"), current_price=D("2400")),
        ]

    def _maps(self) -> dict:
        return {
            "sector_map": {"RELIANCE": "Energy", "TCS": "IT"},
            "beta_map": {"RELIANCE": D("1.10"), "TCS": D("0.85")},
            "div_yield_map": {"RELIANCE": D("0.0030"), "TCS": D("0.0150")},
            "price_history": {},
        }

    def test_returns_locked_top_level_keys(self):
        out = compute_diagnostics(self._two_position_portfolio(), **self._maps())
        for key in (
            "n_positions",
            "total_value_inr",
            "concentration",
            "sector_pct",
            "beta_blend",
            "div_yield",
            "drawdown_1y",
        ):
            assert key in out, f"missing key {key!r}: {out}"

    def test_total_value_correct(self):
        # 100 × 1436 + 50 × 2400 = 143,600 + 120,000 = 263,600.
        out = compute_diagnostics(self._two_position_portfolio(), **self._maps())
        assert out["total_value_inr"] == "263600.00"

    def test_concentration_makes_sense(self):
        out = compute_diagnostics(self._two_position_portfolio(), **self._maps())
        # 2 positions → top_5_pct must be 100.0
        assert out["concentration"]["top_5_pct"] == "100.0"
        # HHI ≈ (143600/263600)² + (120000/263600)² ≈ 0.297 + 0.207 = 0.504
        hhi = float(out["concentration"]["herfindahl"])
        assert 0.49 < hhi < 0.52

    def test_sector_pct_sums_to_100(self):
        out = compute_diagnostics(self._two_position_portfolio(), **self._maps())
        total = sum(float(s["pct"]) for s in out["sector_pct"])
        assert 99.0 <= total <= 101.0

    def test_sector_pct_sorted_desc(self):
        out = compute_diagnostics(self._two_position_portfolio(), **self._maps())
        pcts = [float(s["pct"]) for s in out["sector_pct"]]
        assert pcts == sorted(pcts, reverse=True)

    def test_beta_blend_value_weighted(self):
        # weights ≈ (0.5448 RELIANCE, 0.4552 TCS); beta blend ≈
        # 0.5448*1.10 + 0.4552*0.85 ≈ 0.5993 + 0.3869 = 0.9862
        out = compute_diagnostics(self._two_position_portfolio(), **self._maps())
        beta = float(out["beta_blend"])
        assert 0.97 < beta < 1.0

    def test_div_yield_as_pct(self):
        # Yields stored as 0.0030 / 0.0150 → blend ≈ 0.0085 → as % = 0.85.
        out = compute_diagnostics(self._two_position_portfolio(), **self._maps())
        assert 0.7 < float(out["div_yield"]) < 1.0


# ---------------------------------------------------------------------------
# compute_diagnostics — edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_portfolio(self):
        out = compute_diagnostics(
            [],
            sector_map={},
            beta_map={},
            div_yield_map={},
            price_history={},
        )
        assert out["n_positions"] == 0
        assert out["total_value_inr"] == "0.00"
        assert out["sector_pct"] == []

    def test_missing_quotes_zero_value(self):
        positions = [
            Position("RELIANCE", quantity=100, avg_price=D("1280"), current_price=None),
            Position("TCS", quantity=50, avg_price=D("2150"), current_price=None),
        ]
        out = compute_diagnostics(
            positions,
            sector_map={"RELIANCE": "Energy", "TCS": "IT"},
            beta_map={"RELIANCE": D("1.0"), "TCS": D("0.85")},
            div_yield_map={},
            price_history={},
        )
        assert out["total_value_inr"] == "0.00"
        assert out["concentration"]["top_5_pct"] == "0.0"

    def test_missing_beta_falls_back_to_1(self):
        positions = [
            Position("RELIANCE", quantity=100, avg_price=D("1000"), current_price=D("1000")),
            Position("TCS", quantity=100, avg_price=D("1000"), current_price=D("1000")),
        ]
        out = compute_diagnostics(
            positions,
            sector_map={"RELIANCE": "Energy", "TCS": "IT"},
            beta_map={"RELIANCE": None, "TCS": None},  # all missing
            div_yield_map={"RELIANCE": None, "TCS": None},
            price_history={},
        )
        assert out["beta_blend"] == "1.00"
        assert out["diagnostics_notes"]["missing_beta_count"] == 2

    def test_missing_sector_rolled_to_other(self):
        positions = [
            Position("RELIANCE", quantity=100, avg_price=D("1000"), current_price=D("1000")),
            Position("OBSCURE", quantity=50, avg_price=D("1000"), current_price=D("1000")),
        ]
        out = compute_diagnostics(
            positions,
            sector_map={"RELIANCE": "Energy", "OBSCURE": None},
            beta_map={},
            div_yield_map={},
            price_history={},
        )
        secs = {s["sector"] for s in out["sector_pct"]}
        assert "Other" in secs

    def test_drawdown_handles_no_history(self):
        positions = [
            Position("RELIANCE", quantity=100, avg_price=D("1000"), current_price=D("1000"))
        ]
        out = compute_diagnostics(
            positions,
            sector_map={"RELIANCE": "Energy"},
            beta_map={},
            div_yield_map={},
            price_history={"RELIANCE": []},  # no rows
        )
        # No drawdown computable → 0.0.
        assert float(out["drawdown_1y"]) == 0.0


# ---------------------------------------------------------------------------
# Drawdown — synthetic series
# ---------------------------------------------------------------------------


class TestDrawdown:
    def test_monotone_up_zero_drawdown(self):
        # Single ticker, 30 days, monotone up → drawdown 0.
        positions = [
            Position("X", quantity=1, avg_price=D("100"), current_price=D("130"))
        ]
        history = {
            "X": [(f"2026-01-{d:02d}", D(str(100 + d))) for d in range(1, 31)]
        }
        dd = _drawdown_1y(positions, history)
        assert dd == D("0")

    def test_clear_drawdown_picked_up(self):
        # Up to 200, then down to 100 → drawdown -50%.
        positions = [
            Position("X", quantity=1, avg_price=D("100"), current_price=D("100"))
        ]
        prices = list(range(100, 201)) + list(range(199, 99, -1))  # 200 days
        history = {
            "X": [(f"2026-{1 + i // 30:02d}-{1 + i % 30:02d}", D(str(p)))
                  for i, p in enumerate(prices)]
        }
        # Distinct dates required — fall back to a simple mock.
        history = {
            "X": [(f"2026-01-01T{h:02d}", D(str(p)))  # not real ISO but unique
                  for h, p in enumerate(prices)]
        }
        dd = _drawdown_1y(positions, history)
        # Allow some tolerance — peak 200, trough 100 → -50%.
        assert -0.55 < float(dd) < -0.45

    def test_too_few_dates_returns_zero(self):
        # Less than 30 days → returns 0.
        positions = [Position("X", 1, D("100"), D("100"))]
        history = {"X": [("2026-01-01", D("100")), ("2026-01-02", D("90"))]}
        assert _drawdown_1y(positions, history) == D("0")
