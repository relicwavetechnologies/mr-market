"""Live integration tests for the screener engine (P3-A2).

These hit the real Postgres `mrmarket` database via `SessionLocal`, so they
ONLY run when the local DB is up and the NIFTY-100 + technicals + holdings
backfills have been completed (`uv run python -m scripts.seed_universe`
+ `scripts.backfill_eod` + `scripts.compute_technicals`
+ `scripts.backfill_holdings`).

If the DB isn't reachable we skip — these tests are advisory in CI but
required pre-merge on the developer box.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.analytics.screener import ScreenerError, run_screener
from app.db.session import SessionLocal


async def _skip_unless_db_up() -> None:
    """Per-test DB connectivity check (running asyncio.run at module
    import time confuses pytest-asyncio's loop, so do it lazily)."""
    try:
        async with SessionLocal() as s:
            await s.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        pytest.skip("local Postgres `mrmarket` not reachable")


@pytest.mark.asyncio
async def test_simple_rsi_filter_returns_real_tickers():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        res = await run_screener(session, "rsi_14 < 35", limit=20)
    assert res.universe_size > 0
    # At least some NIFTY-100 names should be in the oversold zone at
    # any given time — but we don't pin the exact list (data is live).
    assert res.matched >= 0
    for hit in res.tickers:
        # Every returned ticker must have rsi_14 in its hits, and it must
        # actually satisfy the predicate.
        assert "rsi_14" in hit.hits, hit
        assert float(hit.hits["rsi_14"]) < 35


@pytest.mark.asyncio
async def test_compound_expression_intersects_correctly():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        res = await run_screener(
            session,
            "rsi_14 > 65 AND promoter_pct > 50",
            limit=50,
        )
    for hit in res.tickers:
        assert float(hit.hits["rsi_14"]) > 65
        assert float(hit.hits["promoter_pct"]) > 50


@pytest.mark.asyncio
async def test_sector_filter_returns_only_that_sector():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        res = await run_screener(session, "sector = 'Energy'", limit=20)
    # Every hit's sector field must equal Energy.
    for hit in res.tickers:
        assert hit.hits.get("sector") == "Energy"
    assert res.matched >= 1, "expected at least 1 Energy stock in NIFTY-100"


@pytest.mark.asyncio
async def test_universe_size_matches_active_stocks():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        res = await run_screener(session, "rsi_14 < 1000", limit=1)
    # NIFTY-100 universe — should be 100. (Allow 50/100 in case the
    # dev box is still on the legacy NIFTY-50 file.)
    assert res.universe_size in (50, 100)


@pytest.mark.asyncio
async def test_explicit_universe_subset():
    """Restricting the universe trims the working set."""
    async with SessionLocal() as session:
        res = await run_screener(
            session,
            "rsi_14 < 1000",
            limit=10,
            universe=["RELIANCE", "TCS", "INFY"],
        )
    assert res.universe_size == 3
    symbols = {t.symbol for t in res.tickers}
    assert symbols.issubset({"RELIANCE", "TCS", "INFY"})


@pytest.mark.asyncio
async def test_unknown_field_raises():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        with pytest.raises(ScreenerError):
            await run_screener(session, "ghost_field < 30")


@pytest.mark.asyncio
async def test_injection_payload_raises():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        with pytest.raises(ScreenerError):
            await run_screener(session, "rsi_14 < 30; DROP TABLE stocks")
