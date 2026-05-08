"""Tests for `POST /research/upload` (drag-drop PDF ingestion).

Drives the FastAPI app via `httpx.AsyncClient + ASGITransport`. We
mock `ingest_pdf` so tests don't depend on OpenAI embeddings or
Pinecone — the goal is to pin the *endpoint contract*: auth gate,
universe gate, multipart shape, file-size cap, error-pass-through
when ingest fails. The real ingest pipeline is exercised by
`scripts.ingest_research` end-to-end on a developer box.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import delete, text

from app.db.models import User
from app.db.session import SessionLocal
from app.main import create_app
from app.security.hash import hash_password
from app.security.tokens import issue_access
from app.workers.research_ingest import IngestStats


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _skip_unless_db_up() -> None:
    try:
        async with SessionLocal() as s:
            await s.execute(text("SELECT 1 FROM stocks LIMIT 1"))
    except Exception:  # noqa: BLE001
        pytest.skip("local Postgres `mrmarket` not reachable")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()),
        base_url="http://test",
    )


async def _make_user(session) -> tuple[User, str]:
    email = f"upload-{uuid.uuid4().hex[:8]}@test.local"
    user = User(
        email=email,
        password_hash=hash_password("secret123"),
        display_name="Upload Tester",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user, issue_access(str(user.id))


def _auth(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


def _fake_pdf_bytes(size: int = 1024) -> bytes:
    """Tiny fake PDF — has the magic bytes but no real text. The endpoint
    only validates suffix + size; ingest_pdf is mocked so parse never runs."""
    return b"%PDF-1.7\n" + (b"x" * (size - 9))


def _stats_ok(ticker: str, fy: str | None = "FY25") -> IngestStats:
    s = IngestStats(ticker=ticker, kind="annual_report", fy=fy)
    s.n_pages = 27
    s.n_chunks = 25
    s.n_embedded = 25
    s.duration_ms = 1234
    return s


def _stats_failed(ticker: str, error: str) -> IngestStats:
    s = IngestStats(ticker=ticker, kind="annual_report", fy="FY25")
    s.error = error
    s.duration_ms = 100
    return s


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_requires_auth():
    await _skip_unless_db_up()
    files = {"file": ("ar.pdf", _fake_pdf_bytes(), "application/pdf")}
    data = {"ticker": "RELIANCE", "title": "Reliance AR FY25"}
    async with _client() as c:
        r = await c.post("/research/upload", data=data, files=files)
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_persists_via_ingest_pdf():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)

    files = {"file": ("ril_ar_fy25.pdf", _fake_pdf_bytes(2048), "application/pdf")}
    data = {
        "ticker": "RELIANCE",
        "title": "Reliance AR FY25",
        "fy": "FY25",
        "kind": "annual_report",
    }
    fake = AsyncMock(return_value=_stats_ok("RELIANCE"))
    with patch("app.api.research.ingest_pdf", fake):
        async with _client() as c:
            r = await c.post(
                "/research/upload",
                data=data,
                files=files,
                headers=_auth(token),
            )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["ticker"] == "RELIANCE"
    assert body["n_pages"] == 27
    assert body["n_chunks"] == 25
    assert body["n_embedded"] == 25
    assert body["uploaded_by"] == str(user.id)
    # ingest_pdf should have been called exactly once with a real Path.
    assert fake.await_count == 1
    call_kwargs = fake.await_args.kwargs
    assert call_kwargs["ticker"] == "RELIANCE"
    assert call_kwargs["fy"] == "FY25"
    assert isinstance(call_kwargs["pdf_path"], Path)
    # Temp file must be cleaned up — the path no longer exists post-ingest.
    assert not call_kwargs["pdf_path"].exists()

    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


# ---------------------------------------------------------------------------
# Universe gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_unknown_ticker_404s():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)

    files = {"file": ("x.pdf", _fake_pdf_bytes(), "application/pdf")}
    data = {"ticker": "GHOSTSTOCK", "title": "X"}
    async with _client() as c:
        r = await c.post(
            "/research/upload", data=data, files=files, headers=_auth(token)
        )
    assert r.status_code == 404
    assert "not in active" in r.json()["detail"]

    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


# ---------------------------------------------------------------------------
# File-format gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_rejects_non_pdf_extension():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)

    files = {"file": ("notes.txt", b"plain text", "text/plain")}
    data = {"ticker": "RELIANCE", "title": "Notes"}
    async with _client() as c:
        r = await c.post(
            "/research/upload", data=data, files=files, headers=_auth(token)
        )
    assert r.status_code == 400
    assert ".pdf" in r.json()["detail"]

    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


@pytest.mark.asyncio
async def test_upload_rejects_unknown_kind():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)

    files = {"file": ("x.pdf", _fake_pdf_bytes(), "application/pdf")}
    data = {"ticker": "RELIANCE", "title": "X", "kind": "garbage"}
    async with _client() as c:
        r = await c.post(
            "/research/upload", data=data, files=files, headers=_auth(token)
        )
    assert r.status_code == 400
    assert "kind" in r.json()["detail"].lower()

    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


@pytest.mark.asyncio
async def test_upload_rejects_empty_file():
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)

    files = {"file": ("empty.pdf", b"", "application/pdf")}
    data = {"ticker": "RELIANCE", "title": "X"}
    async with _client() as c:
        r = await c.post(
            "/research/upload", data=data, files=files, headers=_auth(token)
        )
    assert r.status_code == 400

    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


# ---------------------------------------------------------------------------
# Ingest failure → 200 with ok=False + error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_surfaces_ingest_error():
    """When `ingest_pdf` reports an error in stats.error (e.g. PDF parse
    failed), the endpoint returns 200 with `ok: false` and the error
    message — UI shows a meaningful failure instead of a generic 5xx."""
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)

    files = {"file": ("broken.pdf", _fake_pdf_bytes(), "application/pdf")}
    data = {"ticker": "RELIANCE", "title": "Broken"}
    fake = AsyncMock(
        return_value=_stats_failed("RELIANCE", "pdf_parse: not a PDF")
    )
    with patch("app.api.research.ingest_pdf", fake):
        async with _client() as c:
            r = await c.post(
                "/research/upload",
                data=data,
                files=files,
                headers=_auth(token),
            )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "pdf_parse" in body["error"]

    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


# ---------------------------------------------------------------------------
# Size cap (50 MB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_rejects_oversize_pdf():
    """The endpoint streams in 1 MB chunks and aborts when total > 50 MB.
    Use a small cap-bypass payload that's bigger than 50 MB but tiny in
    real bytes via a stream — but for unit-test simplicity we just send
    a payload over the cap and expect 413."""
    await _skip_unless_db_up()
    async with SessionLocal() as session:
        user, token = await _make_user(session)

    # 51 MB-ish payload. We allocate the bytes (cheap on macOS) — if this
    # ever becomes a CI memory issue we can switch to a chunked file-like.
    big = _fake_pdf_bytes(51 * 1024 * 1024)
    files = {"file": ("huge.pdf", big, "application/pdf")}
    data = {"ticker": "RELIANCE", "title": "Huge"}
    async with _client() as c:
        r = await c.post(
            "/research/upload",
            data=data,
            files=files,
            headers=_auth(token),
        )
    assert r.status_code == 413, r.text

    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()
