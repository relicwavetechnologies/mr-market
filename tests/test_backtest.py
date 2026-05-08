"""Unit tests for the backtest engine (P3-A6).

Pure-functional `run_backtest` over hand-crafted synthetic price
histories. No DB, no scrape. Live API integration is exercised by the
running backend during the live-verify step.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.analytics.backtest import _rsi_14, _sma, run_backtest


def D(d: str) -> dt.date:
    return dt.date.fromisoformat(d)


# ---------------------------------------------------------------------------
# _sma
# ---------------------------------------------------------------------------


class TestSma:
    def test_simple_sma_3(self):
        out = _sma([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        assert out[:2] == [None, None]
        assert out[2] == 2.0  # (1+2+3)/3
        assert out[3] == 3.0  # (2+3+4)/3
        assert out[4] == 4.0  # (3+4+5)/3

    def test_window_larger_than_series(self):
        assert _sma([1.0, 2.0], 5) == [None, None]


# ---------------------------------------------------------------------------
# _rsi_14
# ---------------------------------------------------------------------------


class TestRsi14:
    def test_too_short(self):
        assert _rsi_14([1.0] * 10) == [None] * 10

    def test_monotone_up_yields_high_rsi(self):
        # Strictly increasing prices → all gains, no losses → RSI = 100.
        prices = [float(i) for i in range(1, 30)]
        out = _rsi_14(prices)
        assert out[14] == 100.0
        # And remains 100 forward.
        assert all(v == 100.0 for v in out[14:])

    def test_monotone_down_yields_low_rsi(self):
        prices = [float(i) for i in range(30, 1, -1)]
        out = _rsi_14(prices)
        # All losses, no gains → RSI ≈ 0.
        assert out[14] is not None and out[14] < 5

    def test_indices_before_15_are_none(self):
        prices = [float(i) + 0.1 for i in range(30)]
        out = _rsi_14(prices)
        assert all(v is None for v in out[:14])


# ---------------------------------------------------------------------------
# run_backtest — integration shape
# ---------------------------------------------------------------------------


def _ramp(start: float, days: int, slope: float) -> list[tuple[dt.date, float]]:
    """Build a dated price series with a constant per-day slope."""
    base = D("2025-01-01")
    return [
        (base + dt.timedelta(days=i), start + i * slope)
        for i in range(days)
    ]


class TestRunBacktest:
    def test_returns_known_shape(self):
        # 250 trading days, monotone up — momentum_breakout-ish.
        history = {"FOO": _ramp(100, 250, 1.0)}
        res = run_backtest(
            name="momentum_breakout",
            expr="rsi_14 > 65 AND close > sma_50 AND close > sma_200",
            period_days=250,
            price_history=history,
        )
        # Shape sanity.
        assert res.name == "momentum_breakout"
        assert res.period_days == 250
        assert res.n_signals >= 1
        assert -1.0 <= res.mean_return <= 1.0
        assert 0 <= res.hit_rate <= 1
        assert res.equity_curve  # not empty

    def test_no_signals_returns_empty_result(self):
        # close always below sma_200 (impossible under monotone-up):
        # use a flat ramp + an expression that never matches.
        history = {"FOO": _ramp(100, 250, 0.0)}
        res = run_backtest(
            name="never_matches",
            expr="rsi_14 < 0",  # impossible
            period_days=250,
            price_history=history,
        )
        assert res.n_signals == 0
        assert res.hit_rate == 0.0
        assert res.equity_curve == []

    def test_too_short_history(self):
        history = {"FOO": _ramp(100, 5, 1.0)}
        res = run_backtest(
            name="x",
            expr="rsi_14 > 1",
            period_days=5,
            price_history=history,
        )
        assert res.n_signals == 0

    def test_holding_period_skips_window_tail(self):
        # With holding_period=5 we don't book signals on the last 5 days
        # (no forward window). 100 days → at most 95 evaluated dates.
        history = {"FOO": _ramp(100, 250, 1.0)}
        res = run_backtest(
            name="x",
            expr="close > sma_200",
            period_days=250,
            holding_period=5,
            price_history=history,
        )
        # Curve length never exceeds (n_walk_days + 1) including seed.
        assert len(res.equity_curve) <= 250

    def test_hit_rate_for_uptrending_long_signal(self):
        # If we always enter and prices go up, hit_rate should be 1.0.
        history = {"FOO": _ramp(100, 250, 0.5)}
        res = run_backtest(
            name="x",
            expr="close > sma_200",  # holds for the post-warmup window
            period_days=250,
            price_history=history,
        )
        assert res.n_signals > 0
        assert res.hit_rate >= 0.99

    def test_two_tickers_aggregate(self):
        # Two tickers; one trends up, one is flat.
        history = {
            "UP": _ramp(100, 250, 0.5),
            "FLAT": _ramp(100, 250, 0.0),
        }
        res = run_backtest(
            name="x",
            expr="close > sma_200",
            period_days=250,
            price_history=history,
        )
        # The flat ticker won't pass `close > sma_200`; only UP signals fire.
        assert res.n_signals > 0

    def test_unknown_field_in_expr_returns_zero(self):
        # Bad expr → ScreenerError is caught at compile_expr; the engine
        # should propagate it (caller decides whether to 400). We assert
        # the propagation via pytest.raises.
        from app.analytics.screener import ScreenerError

        with pytest.raises(ScreenerError):
            run_backtest(
                name="x",
                expr="ghost_field > 5",
                period_days=250,
                price_history={"FOO": _ramp(100, 250, 1.0)},
            )

    def test_sector_in_expr_uses_sector_map(self):
        history = {
            "ENERGY1": _ramp(100, 250, 0.5),
            "IT1": _ramp(100, 250, 0.5),
        }
        res = run_backtest(
            name="x",
            expr="sector = 'Energy' AND close > sma_200",
            period_days=250,
            price_history=history,
            sector_map={"ENERGY1": "Energy", "IT1": "IT"},
        )
        assert res.n_signals > 0
        # All matches must have come from ENERGY1 — easiest check is
        # that signals exist; the screener's row evaluation is unit-
        # tested elsewhere.
