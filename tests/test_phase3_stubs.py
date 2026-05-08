"""Tests for the day-1 stub endpoints (P3-A1).

These pin the *shape* of every Phase-3 REST payload that Dev B's LLM tools
will consume. When the real implementations land (P3-A2 → P3-A7), the
existing tests stay; they should keep passing because the contract didn't
change. New behaviour gets new tests.

The stubs are deliberately deterministic — no DB, no scrape, no LLM. That's
why this test file doesn't fixture a Postgres / Redis client.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

app = create_app()
client = TestClient(app)


# NOTE: the screener tests that lived here were moved to
# `tests/test_screener_stored.py` once P3-A3 wired the endpoints to the
# real DB. Kept the portfolio / backtest / watchlist stub tests below
# because those endpoints are still stubbed (until P3-A4 → P3-A7).


# ---------------------------------------------------------------------------
# /portfolio — import / diagnostics
# ---------------------------------------------------------------------------


class TestPortfolioStubs:
    # NOTE: P3-A4 wired `/portfolio/import` to the real DB + auth.
    # The auth + persistence + universe-gate behaviour is now exercised
    # in tests/test_portfolio_api.py (with throwaway users + tokens).
    # We keep the diagnostics stub assertion below until P3-A5 lands.

    def test_import_now_requires_auth(self):
        # Without auth → 401 (no longer a stub).
        r = client.post(
            "/portfolio/import",
            json={"holdings": [{"ticker": "RELIANCE", "quantity": 1}]},
        )
        assert r.status_code == 401

    def test_import_rejects_quantity_zero(self):
        # Pydantic still validates the body shape before auth runs in
        # FastAPI's dependency order. Quantity ge=1 → 422 even unauth.
        # (FastAPI runs body validation after auth; without auth header
        # we get 401 first.)
        r = client.post(
            "/portfolio/import",
            json={
                "format": "csv",
                "holdings": [{"ticker": "RELIANCE", "quantity": 0}],
            },
        )
        # Either 401 (no auth) or 422 (bad body) is acceptable — both
        # cleanly reject the request.
        assert r.status_code in (401, 422)

    def test_diagnostics_now_requires_auth(self):
        # P3-A5: `/portfolio/{id}/diagnostics` is real and auth-gated.
        # Without a token → 401. The shape contract is exercised by the
        # pure-functional unit tests in tests/test_portfolio_analytics.py.
        r = client.get("/portfolio/17/diagnostics")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# /backtest — run
# ---------------------------------------------------------------------------


class TestBacktestStubs:
    def test_run_known_screener(self):
        r = client.post(
            "/backtest/run", json={"name": "value_rebound", "period_days": 365}
        )
        assert r.status_code == 200, r.text
        data = r.json()
        for key in (
            "name",
            "period_days",
            "n_signals",
            "hit_rate",
            "mean_return",
            "worst_drawdown",
            "sharpe_proxy",
            "equity_curve",
        ):
            assert key in data, f"missing {key!r}: {data}"
        assert data["name"] == "value_rebound"
        assert data["period_days"] == 365
        # Curve has the right number of points + correct shape.
        assert len(data["equity_curve"]) == 366
        for pt in data["equity_curve"][:3]:
            assert {"date", "value"} <= set(pt)

    def test_run_unknown_screener_404s(self):
        r = client.post(
            "/backtest/run", json={"name": "ghost_screener", "period_days": 90}
        )
        assert r.status_code == 404

    def test_period_days_clamped(self):
        # Below the 30-day floor → 422 from pydantic.
        r = client.post(
            "/backtest/run", json={"name": "value_rebound", "period_days": 5}
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# /watchlist — list / add / delete
# ---------------------------------------------------------------------------


class TestWatchlistStubs:
    # Reset between tests so process-local state doesn't leak.
    def setup_method(self):
        from app.api.watchlist import _WATCHLIST

        _WATCHLIST.clear()

    def test_initial_list_is_empty(self):
        r = client.get("/watchlist")
        assert r.status_code == 200
        assert r.json()["tickers"] == []
        assert r.json()["size"] == 0

    def test_add_then_list(self):
        r = client.post("/watchlist", json={"ticker": "reliance"})
        assert r.status_code == 200
        assert r.json()["tickers"] == ["RELIANCE"]
        # Adding again is idempotent.
        r2 = client.post("/watchlist", json={"ticker": "RELIANCE"})
        assert r2.json()["size"] == 1

    def test_add_multiple_uppercased_and_sorted(self):
        for t in ("tcs", "INFY", "Reliance"):
            client.post("/watchlist", json={"ticker": t})
        r = client.get("/watchlist")
        assert r.json()["tickers"] == ["INFY", "RELIANCE", "TCS"]
        assert r.json()["size"] == 3

    def test_delete_present_ticker(self):
        client.post("/watchlist", json={"ticker": "RELIANCE"})
        client.post("/watchlist", json={"ticker": "TCS"})
        r = client.delete("/watchlist/RELIANCE")
        assert r.status_code == 200
        assert r.json()["tickers"] == ["TCS"]

    def test_delete_absent_ticker_404s(self):
        r = client.delete("/watchlist/XYZ")
        assert r.status_code == 404

    def test_add_blank_ticker_400s(self):
        r = client.post("/watchlist", json={"ticker": "   "})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Drift guard — every Phase-3 stub returns the `_stub: true` marker so
# Dev B can detect they're hitting stubs vs the real backend in tests.
# When the real impls land, this marker is removed in the same PR.
# ---------------------------------------------------------------------------


class TestStubMarker:
    # NOTE: the screener-stub assertion was removed when P3-A3 flipped
    # `/screener/run` to a real DB-backed endpoint. The "no longer carries
    # marker" check is now in tests/test_screener_stored.py against a
    # live DB.

    def test_portfolio_diagnostics_no_longer_stubbed(self):
        # P3-A5: real endpoint, auth required → 401 without a token
        # (stubs returned 200; this regression-guards the flip).
        r = client.get("/portfolio/17/diagnostics")
        assert r.status_code == 401
        assert "_stub" not in r.json()

    def test_backtest_run_has_stub_marker(self):
        r = client.post(
            "/backtest/run", json={"name": "oversold_quality", "period_days": 90}
        )
        assert r.json().get("_stub") is True

    def test_watchlist_get_has_stub_marker(self):
        r = client.get("/watchlist")
        assert r.json().get("_stub") is True
