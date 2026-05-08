"""Tests for watchlist persistence + daily-digest builder (P3-A7).

The pure-functional digest builder is unit-tested without DB or Redis.
The HTTP endpoints (auth-gated, persisted) are exercised via
ASGITransport with a fresh user per test.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import delete, text

from app.db.models import User, Watchlist
from app.db.session import SessionLocal
from app.main import create_app
from app.security.hash import hash_password
from app.security.tokens import issue_access
from app.workers.watchlist_digest import (
    UserDigest,
    _change_pct,
    build_digest,
    digest_to_json,
)


# ---------------------------------------------------------------------------
# Pure-functional digest builder
# ---------------------------------------------------------------------------


class TestChangePct:
    def test_normal(self):
        assert _change_pct(110, 100) == 10.0

    def test_negative(self):
        assert _change_pct(90, 100) == -10.0

    def test_none_prev(self):
        assert _change_pct(100, None) is None

    def test_zero_prev_returns_none(self):
        assert _change_pct(100, 0) is None


class TestBuildDigest:
    def test_two_movers(self):
        latest = {
            "RELIANCE": (dt.date(2026, 5, 8), Decimal("1450")),
            "TCS": (dt.date(2026, 5, 8), Decimal("2400")),
        }
        prev = {"RELIANCE": Decimal("1430"), "TCS": Decimal("2380")}
        d = build_digest("u1", ["RELIANCE", "TCS"], latest, prev)
        assert d.user_id == "u1"
        assert len(d.tickers) == 2
        # 1450/1430 = +1.4% → mover; 2400/2380 = +0.84% → not (under 1%)
        assert d.n_movers == 1

    def test_threshold_configurable(self):
        latest = {"X": (dt.date(2026, 5, 8), Decimal("110"))}
        prev = {"X": Decimal("100")}
        # 10% move always → mover regardless of threshold.
        d = build_digest("u1", ["X"], latest, prev, mover_threshold_pct=15.0)
        assert d.n_movers == 0  # threshold is 15, move was 10

    def test_missing_prev_close_handled(self):
        latest = {"X": (dt.date(2026, 5, 8), Decimal("100"))}
        d = build_digest("u1", ["X"], latest, {})
        assert d.tickers[0].change_pct is None
        assert d.n_movers == 0

    def test_ticker_with_no_latest_close_dropped(self):
        d = build_digest("u1", ["GHOST"], {}, {})
        assert d.tickers == []
        assert d.as_of == ""


class TestDigestToJson:
    def test_serialises_decimals_as_strings(self):
        latest = {"X": (dt.date(2026, 5, 8), Decimal("100.5"))}
        prev = {"X": Decimal("99.0")}
        d = build_digest("u1", ["X"], latest, prev)
        j = digest_to_json(d)
        assert j["user_id"] == "u1"
        assert j["tickers"][0]["close"] == "100.5"
        assert j["tickers"][0]["prev_close"] == "99.0"


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


async def _skip_unless_db_up() -> None:
    try:
        async with SessionLocal() as s:
            await s.execute(text("SELECT 1 FROM watchlist LIMIT 1"))
    except Exception:  # noqa: BLE001
        pytest.skip("local Postgres `mrmarket` (with watchlist table) not reachable")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()),
        base_url="http://test",
    )


async def _make_user(session) -> tuple[User, str]:
    email = f"a7-{uuid.uuid4().hex[:8]}@test.local"
    user = User(
        email=email,
        password_hash=hash_password("secret123"),
        display_name="A-7 Tester",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user, issue_access(str(user.id))


def _auth(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_watchlist_unauthorized():
    await _skip_unless_db_up()
    async with _client() as c:
        r = await c.get("/watchlist")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_watchlist_initially_empty():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)
    async with _client() as c:
        r = await c.get("/watchlist", headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == {"ok": True, "tickers": [], "size": 0}
    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


@pytest.mark.asyncio
async def test_watchlist_add_and_list():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)
    async with _client() as c:
        r1 = await c.post(
            "/watchlist", json={"ticker": "reliance"}, headers=_auth(token)
        )
        assert r1.status_code == 200
        assert r1.json()["tickers"] == ["RELIANCE"]
        # Idempotent re-add.
        r2 = await c.post(
            "/watchlist", json={"ticker": "RELIANCE"}, headers=_auth(token)
        )
        assert r2.json()["size"] == 1
        # Add a second ticker.
        r3 = await c.post(
            "/watchlist", json={"ticker": "TCS"}, headers=_auth(token)
        )
        assert r3.json()["tickers"] == ["RELIANCE", "TCS"]
    async with SessionLocal() as session:
        await session.execute(delete(Watchlist).where(Watchlist.user_id == user.id))
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


@pytest.mark.asyncio
async def test_watchlist_universe_gate():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)
    async with _client() as c:
        r = await c.post(
            "/watchlist", json={"ticker": "GHOSTSTOCK"}, headers=_auth(token)
        )
    assert r.status_code == 404
    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


@pytest.mark.asyncio
async def test_watchlist_remove():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)
    async with _client() as c:
        await c.post("/watchlist", json={"ticker": "RELIANCE"}, headers=_auth(token))
        await c.post("/watchlist", json={"ticker": "TCS"}, headers=_auth(token))
        r = await c.delete("/watchlist/RELIANCE", headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["tickers"] == ["TCS"]
        # Removing again → 404.
        r2 = await c.delete("/watchlist/RELIANCE", headers=_auth(token))
        assert r2.status_code == 404
    async with SessionLocal() as session:
        await session.execute(delete(Watchlist).where(Watchlist.user_id == user.id))
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


@pytest.mark.asyncio
async def test_watchlist_isolated_per_user():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user_a, token_a = await _make_user(session)
        user_b, token_b = await _make_user(session)
    async with _client() as c:
        await c.post(
            "/watchlist", json={"ticker": "RELIANCE"}, headers=_auth(token_a)
        )
        # User B sees an empty list — A's add must not leak.
        r = await c.get("/watchlist", headers=_auth(token_b))
    assert r.json()["tickers"] == []
    async with SessionLocal() as session:
        await session.execute(
            delete(Watchlist).where(Watchlist.user_id.in_([user_a.id, user_b.id]))
        )
        await session.execute(
            delete(User).where(User.id.in_([user_a.id, user_b.id]))
        )
        await session.commit()
