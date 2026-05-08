"""Tests for the stored-screeners surface (P3-A3).

Drives the FastAPI app via `httpx.AsyncClient + ASGITransport` so the
async DB session and pytest-asyncio share an event loop. Skips when the
local Postgres `mrmarket` (with the `screeners` table seeded) isn't
reachable.

Two pieces are pinned here:
1. The 6 seed packs landed by the migration are present, parseable, and
   actually return results against the real NIFTY-100 universe.
2. The `name` path on `POST /screener/run` resolves the saved expression
   from `screeners` and runs the same engine.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import text

from app.analytics.screener import compile_expr
from app.db.session import SessionLocal
from app.main import create_app


SEED_NAMES = {
    "oversold_quality",
    "value_rebound",
    "momentum_breakout",
    "high_pledge_avoid",
    "fii_buying",
    "promoter_increasing",
}


async def _skip_unless_db_up() -> None:
    try:
        async with SessionLocal() as s:
            await s.execute(text("SELECT 1 FROM screeners LIMIT 1"))
    except Exception:  # noqa: BLE001
        pytest.skip("local Postgres `mrmarket` (with screeners table) not reachable")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()),
        base_url="http://test",
    )


# ---------------------------------------------------------------------------
# 1. GET /screener/list — seed packs landed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_all_six_seed_packs():
    await _skip_unless_db_up()
    async with _client() as c:
        r = await c.get("/screener/list")
    assert r.status_code == 200
    screeners = r.json()["screeners"]
    names = {s["name"] for s in screeners}
    assert SEED_NAMES <= names

    seeds = [s for s in screeners if s["name"] in SEED_NAMES]
    for s in seeds:
        assert {"name", "expr", "description", "is_seed", "created_by"} <= set(s)
        assert s["is_seed"] is True
        assert s["created_by"] is None


# ---------------------------------------------------------------------------
# 2. Every seed pack expression compiles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_seed_pack_expressions_compile():
    await _skip_unless_db_up()
    async with _client() as c:
        r = await c.get("/screener/list")
    for s in r.json()["screeners"]:
        compile_expr(s["expr"])


# ---------------------------------------------------------------------------
# 3. GET /screener/{name}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_each_seed_pack():
    await _skip_unless_db_up()
    async with _client() as c:
        for name in SEED_NAMES:
            r = await c.get(f"/screener/{name}")
            assert r.status_code == 200, (name, r.text)
            data = r.json()
            assert data["name"] == name
            assert data["is_seed"] is True
            assert isinstance(data["expr"], str) and data["expr"].strip()


@pytest.mark.asyncio
async def test_get_unknown_screener_404s():
    await _skip_unless_db_up()
    async with _client() as c:
        r = await c.get("/screener/__nope__")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 4. POST /screener/run — name path runs against real DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_each_seed_pack_returns_locked_shape():
    await _skip_unless_db_up()
    async with _client() as c:
        for name in SEED_NAMES:
            r = await c.post(
                "/screener/run", json={"name": name, "limit": 10}
            )
            assert r.status_code == 200, (name, r.text)
            data = r.json()
            assert {"matched", "universe_size", "exec_ms", "tickers"} <= set(data)
            assert data["universe_size"] >= 50
            assert isinstance(data["tickers"], list)
            for t in data["tickers"]:
                assert {"symbol", "score", "hits"} <= set(t)
            assert "_stub" not in data, name


@pytest.mark.asyncio
async def test_run_unknown_name_404s():
    await _skip_unless_db_up()
    async with _client() as c:
        r = await c.post("/screener/run", json={"name": "__nope__"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_run_oversold_quality_actually_filters():
    """`oversold_quality` is `rsi_14 < 35 AND promoter_pct > 50`. Verify
    every returned ticker really has both fields satisfied."""
    await _skip_unless_db_up()
    async with _client() as c:
        r = await c.post(
            "/screener/run", json={"name": "oversold_quality", "limit": 50}
        )
    data = r.json()
    for t in data["tickers"]:
        assert float(t["hits"]["rsi_14"]) < 35, t
        assert float(t["hits"]["promoter_pct"]) > 50, t


@pytest.mark.asyncio
async def test_run_momentum_breakout_actually_filters():
    """`momentum_breakout`: rsi_14 > 65 AND close > sma_50 AND close > sma_200."""
    await _skip_unless_db_up()
    async with _client() as c:
        r = await c.post(
            "/screener/run", json={"name": "momentum_breakout", "limit": 50}
        )
    data = r.json()
    for t in data["tickers"]:
        rsi = float(t["hits"]["rsi_14"])
        close = float(t["hits"]["close"])
        sma_50 = float(t["hits"]["sma_50"])
        sma_200 = float(t["hits"]["sma_200"])
        assert rsi > 65, t
        assert close > sma_50, t
        assert close > sma_200, t


# ---------------------------------------------------------------------------
# 5. Equivalence — running `name` is the same as running its `expr`
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_name_path_equivalent_to_inline_expr():
    """Resolving `oversold_quality` via the `name` path must produce the
    same matched set as passing its raw `expr` directly."""
    await _skip_unless_db_up()
    async with _client() as c:
        s = (await c.get("/screener/oversold_quality")).json()
        raw = s["expr"]

        by_name = (
            await c.post(
                "/screener/run", json={"name": "oversold_quality", "limit": 100}
            )
        ).json()
        by_expr = (
            await c.post(
                "/screener/run", json={"expr": raw, "limit": 100}
            )
        ).json()
    assert {t["symbol"] for t in by_name["tickers"]} == {
        t["symbol"] for t in by_expr["tickers"]
    }
