"""Unit tests for the vector-store abstraction.

The Pinecone path is exercised against a fake client so we never hit the
network or burn API quota in CI. Network-only behaviour (index creation,
real upsert latency) is covered by the live ingest run, not here.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.rag.vector_store import PineconeStore, get_store


# ---------------------------------------------------------------------------
# Fake Pinecone client
# ---------------------------------------------------------------------------


class _FakeIndex:
    """In-memory stand-in for `pinecone.Index`. Captures upserts and serves
    deterministic query responses we control."""

    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []
        self.queries: list[dict[str, Any]] = []
        self.canned_query_response: dict[str, Any] = {"matches": []}

    def upsert(self, *, vectors: list[dict[str, Any]], namespace: str) -> dict[str, int]:
        self.upserts.append({"namespace": namespace, "vectors": vectors})
        return {"upserted_count": len(vectors)}

    def query(
        self,
        *,
        namespace: str,
        vector: list[float],
        top_k: int,
        include_metadata: bool,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.queries.append(
            {
                "namespace": namespace,
                "top_k": top_k,
                "include_metadata": include_metadata,
                "filter": filter,
            }
        )
        return self.canned_query_response


def _make_store_with_fake_index() -> tuple[PineconeStore, _FakeIndex]:
    store = PineconeStore()
    fake = _FakeIndex()
    # Skip _ensure_index entirely — inject the fake.
    store._index = fake  # type: ignore[attr-defined]
    return store, fake


# ---------------------------------------------------------------------------
# Pinecone — vector ID + namespace conventions
# ---------------------------------------------------------------------------


class TestPineconeIdNamespace:
    def test_vector_id(self):
        assert PineconeStore._vector_id(42, 7) == "42:7"

    def test_namespace_uppercases_ticker(self):
        assert PineconeStore._namespace("reliance") == "RELIANCE"

    def test_namespace_strips_whitespace(self):
        assert PineconeStore._namespace("  TCS  ") == "TCS"

    def test_namespace_falls_back_when_blank(self):
        assert PineconeStore._namespace("") == "_default"
        assert PineconeStore._namespace("   ") == "_default"


# ---------------------------------------------------------------------------
# Pinecone — upsert
# ---------------------------------------------------------------------------


class TestPineconeUpsert:
    @pytest.mark.asyncio
    async def test_no_chunks_returns_zero(self):
        store, fake = _make_store_with_fake_index()
        n = await store.upsert(document_id=1, chunks=[], ticker="RELIANCE")
        assert n == 0
        assert fake.upserts == []

    @pytest.mark.asyncio
    async def test_writes_each_chunk_under_per_ticker_namespace(self):
        store, fake = _make_store_with_fake_index()
        chunks = [
            (0, [0.1] * 1536, {"kind": "annual_report", "fy": "FY25", "page": 1}),
            (1, [0.2] * 1536, {"kind": "annual_report", "fy": "FY25", "page": 2}),
        ]
        n = await store.upsert(document_id=42, chunks=chunks, ticker="reliance")
        assert n == 2
        assert len(fake.upserts) == 1
        batch = fake.upserts[0]
        assert batch["namespace"] == "RELIANCE"
        assert len(batch["vectors"]) == 2
        ids = {v["id"] for v in batch["vectors"]}
        assert ids == {"42:0", "42:1"}
        # metadata must include document_id and chunk_idx so we can resolve back
        for v in batch["vectors"]:
            assert v["metadata"]["document_id"] == 42
            assert v["metadata"]["ticker"] == "RELIANCE"
            assert "chunk_idx" in v["metadata"]

    @pytest.mark.asyncio
    async def test_drops_none_metadata_values(self):
        # Pinecone rejects None-valued metadata fields on some SDK versions.
        store, fake = _make_store_with_fake_index()
        await store.upsert(
            document_id=1,
            chunks=[(0, [0.0] * 1536, {"kind": "annual_report", "fy": None, "page": 1})],
            ticker="X",
        )
        meta = fake.upserts[0]["vectors"][0]["metadata"]
        assert "fy" not in meta
        assert meta["page"] == 1

    @pytest.mark.asyncio
    async def test_batches_at_100_vectors(self):
        store, fake = _make_store_with_fake_index()
        chunks = [(i, [0.0] * 1536, {"kind": "x"}) for i in range(250)]
        await store.upsert(document_id=1, chunks=chunks, ticker="X")
        # 250 vectors → 3 batches (100 + 100 + 50)
        assert len(fake.upserts) == 3
        assert sum(len(b["vectors"]) for b in fake.upserts) == 250


# ---------------------------------------------------------------------------
# Pinecone — search → resolves text from Postgres
# ---------------------------------------------------------------------------


class TestPineconeSearch:
    @pytest.mark.asyncio
    async def test_empty_matches_returns_empty(self):
        store, fake = _make_store_with_fake_index()
        fake.canned_query_response = {"matches": []}
        # Session won't be used because we short-circuit on empty matches.
        out = await store.search(
            session=None,  # type: ignore[arg-type]
            ticker="RELIANCE",
            query_embedding=[0.1] * 1536,
            top_k=5,
            kinds=None,
        )
        assert out == []
        assert fake.queries[0]["namespace"] == "RELIANCE"
        assert fake.queries[0]["top_k"] == 5
        assert fake.queries[0]["filter"] is None

    @pytest.mark.asyncio
    async def test_kinds_filter_is_passed(self):
        store, fake = _make_store_with_fake_index()
        fake.canned_query_response = {"matches": []}
        await store.search(
            session=None,  # type: ignore[arg-type]
            ticker="RELIANCE",
            query_embedding=[0.1] * 1536,
            top_k=3,
            kinds=["annual_report"],
        )
        assert fake.queries[0]["filter"] == {"kind": {"$in": ["annual_report"]}}


# ---------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------


class TestSelector:
    def test_default_is_jsonb(self, monkeypatch):
        monkeypatch.setenv("VECTOR_BACKEND", "jsonb")
        from app.config import get_settings

        get_settings.cache_clear()  # type: ignore[attr-defined]
        store = get_store()
        assert store.name == "jsonb"

    def test_pinecone_selected_when_key_set(self, monkeypatch):
        monkeypatch.setenv("VECTOR_BACKEND", "pinecone")
        monkeypatch.setenv("PINECONE_API_KEY", "fake-key")
        from app.config import get_settings

        get_settings.cache_clear()  # type: ignore[attr-defined]
        store = get_store()
        assert store.name == "pinecone"

    def test_pinecone_falls_back_when_key_missing(self, monkeypatch):
        monkeypatch.setenv("VECTOR_BACKEND", "pinecone")
        monkeypatch.setenv("PINECONE_API_KEY", "")
        from app.config import get_settings

        get_settings.cache_clear()  # type: ignore[attr-defined]
        store = get_store()
        assert store.name == "jsonb"
