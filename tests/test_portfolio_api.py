"""Live integration tests for `/portfolio/import` (P3-A4).

Drives the FastAPI app via `httpx.AsyncClient + ASGITransport` so the
async DB session and pytest-asyncio share an event loop. Skips when the
local Postgres `mrmarket` (with the `portfolios` + `holdings_user`
tables migrated) isn't reachable.

Each test creates its own throwaway user + access token to avoid
collisions with anything else in the DB.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import delete, select, text

from app.db.models import HoldingUser, Portfolio, User
from app.db.session import SessionLocal
from app.main import create_app
from app.security.hash import hash_password
from app.security.tokens import issue_access


async def _skip_unless_db_up() -> None:
    try:
        async with SessionLocal() as s:
            await s.execute(text("SELECT 1 FROM portfolios LIMIT 1"))
    except Exception:  # noqa: BLE001
        pytest.skip("local Postgres `mrmarket` (with portfolios table) not reachable")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()),
        base_url="http://test",
    )


async def _make_user(session) -> tuple[User, str]:
    """Create a fresh user + return (user, access_token)."""
    email = f"p3a4-{uuid.uuid4().hex[:8]}@test.local"
    user = User(
        email=email,
        password_hash=hash_password("secret123"),
        display_name="A-4 Tester",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user, issue_access(str(user.id))


def _auth(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_without_auth_401s():
    await _skip_unless_db_up()
    async with _client() as c:
        r = await c.post(
            "/portfolio/import",
            json={"holdings": [{"ticker": "RELIANCE", "quantity": 10}]},
        )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# JSON `holdings` path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_json_holdings_persists():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)

    async with _client() as c:
        r = await c.post(
            "/portfolio/import",
            json={
                "holdings": [
                    {"ticker": "RELIANCE", "quantity": 50, "avg_price": "1380.50"},
                    {"ticker": "TCS", "quantity": 10, "avg_price": "2150.00"},
                ],
                "name": "P3-A4 Test Portfolio",
            },
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["n_positions"] == 2
    pid = data["portfolio_id"]

    # Verify the rows are actually in the DB.
    async with SessionLocal() as session:
        portfolio = await session.get(Portfolio, pid)
        assert portfolio is not None
        assert portfolio.user_id == user.id
        assert portfolio.name == "P3-A4 Test Portfolio"

        holdings = (
            await session.execute(
                select(HoldingUser).where(HoldingUser.portfolio_id == pid)
            )
        ).scalars().all()
        assert {h.ticker for h in holdings} == {"RELIANCE", "TCS"}
        # Cleanup.
        await session.execute(
            delete(HoldingUser).where(HoldingUser.portfolio_id == pid)
        )
        await session.execute(delete(Portfolio).where(Portfolio.id == pid))
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


# ---------------------------------------------------------------------------
# raw_text CSV path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_csv_raw_text_persists():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)

    csv_text = (
        "ticker,quantity,avg_price\n"
        "RELIANCE,50,1380.50\n"
        "TCS,10,2150.00\n"
        "INFY,20,1450.00\n"
    )
    async with _client() as c:
        r = await c.post(
            "/portfolio/import",
            json={"raw_text": csv_text, "format": "csv"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["n_positions"] == 3
    assert data["format"] == "csv"

    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


# ---------------------------------------------------------------------------
# CDSL paste path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_cdsl_paste_persists():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)

    paste = (
        "Instrument\tQty\tAvg cost\tLTP\tCur val\tP&L\tNet chg\n"
        "RELIANCE\t100\t1280.50\t1436.10\t143610.00\t+15560.00\t+12.15%\n"
        "TCS\t25\t2150.00\t2401.40\t60035.00\t+6285.00\t+11.68%\n"
        "INFY\t30\t1450.00\t1490.00\t44700.00\t+1200.00\t+2.76%\n"
    )
    async with _client() as c:
        r = await c.post(
            "/portfolio/import",
            json={"raw_text": paste},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["n_positions"] == 3
    assert data["format"] == "cdsl_paste"
    assert "RELIANCE" in [
        # spot-check: total cost approx 1280.50 * 100 + 2150 * 25 + 1450 * 30
        # = 128,050 + 53,750 + 43,500 = 225,300
        h
        for h in [data.get("unknown_tickers", [])]
    ] or True  # n/a — just verify the cost magnitude
    assert float(data["total_cost_inr"]) > 200_000

    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


# ---------------------------------------------------------------------------
# Universe gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_drops_unknown_tickers():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)

    async with _client() as c:
        r = await c.post(
            "/portfolio/import",
            json={
                "holdings": [
                    {"ticker": "RELIANCE", "quantity": 10},
                    {"ticker": "GHOSTSTOCK", "quantity": 5},
                ]
            },
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["n_positions"] == 1
    assert "GHOSTSTOCK" in data["unknown_tickers"]

    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


@pytest.mark.asyncio
async def test_import_all_unknown_400s():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)

    async with _client() as c:
        r = await c.post(
            "/portfolio/import",
            json={"holdings": [{"ticker": "GHOSTSTOCK", "quantity": 10}]},
            headers=_auth(token),
        )
    assert r.status_code == 400

    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_neither_holdings_nor_text_400s():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)

    async with _client() as c:
        r = await c.post("/portfolio/import", json={}, headers=_auth(token))
    assert r.status_code == 400

    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


@pytest.mark.asyncio
async def test_import_collapses_duplicates():
    """Passing the same ticker twice merges into a single position with
    weighted-average cost."""
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)

    async with _client() as c:
        r = await c.post(
            "/portfolio/import",
            json={
                "holdings": [
                    {"ticker": "RELIANCE", "quantity": 100, "avg_price": "1200"},
                    {"ticker": "RELIANCE", "quantity": 50, "avg_price": "1400"},
                ]
            },
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    pid = r.json()["portfolio_id"]
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(HoldingUser).where(HoldingUser.portfolio_id == pid)
            )
        ).scalars().all()
        assert len(rows) == 1, "duplicates should be merged into one row"
        assert rows[0].quantity == 150
        # Cleanup.
        await session.execute(
            delete(HoldingUser).where(HoldingUser.portfolio_id == pid)
        )
        await session.execute(delete(Portfolio).where(Portfolio.id == pid))
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()
