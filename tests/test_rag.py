"""Unit tests for RAG primitives — `chunking` (pure) and `retrieval.cosine`
(pure, mock embeddings).

The PDF / OpenAI paths are exercised by the live ingest in
`scripts.ingest_research`. Here we only cover the deterministic logic.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.rag.chunking import (
    DEFAULT_CHUNK_CHARS,
    DEFAULT_OVERLAP_CHARS,
    Chunk,
    PageText,
    chunk_pages,
)
from app.rag.retrieval import RetrievedChunk, cosine, to_dict


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------


class TestChunkPages:
    def test_empty_pages(self):
        assert chunk_pages([]) == []

    def test_single_short_page(self):
        pages = [PageText(page=1, text="hello world")]
        chunks = chunk_pages(pages, chunk_chars=50, overlap_chars=5)
        assert len(chunks) == 1
        assert chunks[0].chunk_idx == 0
        assert chunks[0].page == 1
        assert "hello world" in chunks[0].text
        assert chunks[0].pages_spanned == (1,)

    def test_long_page_produces_overlapping_chunks(self):
        # 100-char page, chunk=40, overlap=10 → step=30 → ~ceil((100-10)/30) = 3-4 chunks
        text = "a" * 100
        chunks = chunk_pages([PageText(1, text)], chunk_chars=40, overlap_chars=10)
        assert len(chunks) >= 3
        # Adjacent chunks must share the overlap region (last 10 chars of n == first 10 of n+1).
        for a, b in zip(chunks, chunks[1:], strict=False):
            assert a.text[-10:] == b.text[:10]

    def test_multi_page_records_pages_spanned(self):
        # Each page is well within one chunk; chunk_chars large
        pages = [
            PageText(1, "page one content"),
            PageText(2, "page two content"),
            PageText(3, "page three content"),
        ]
        chunks = chunk_pages(pages, chunk_chars=200, overlap_chars=0)
        assert len(chunks) == 1
        assert chunks[0].pages_spanned == (1, 2, 3)

    def test_chunk_idx_is_monotonic(self):
        pages = [PageText(1, "x" * 5000)]
        chunks = chunk_pages(pages)
        for i, c in enumerate(chunks):
            assert c.chunk_idx == i

    def test_invalid_overlap_raises(self):
        with pytest.raises(ValueError):
            chunk_pages([PageText(1, "x")], chunk_chars=100, overlap_chars=200)

    def test_invalid_chunk_size_raises(self):
        with pytest.raises(ValueError):
            chunk_pages([PageText(1, "x")], chunk_chars=0)

    def test_token_estimate_proportional_to_chars(self):
        pages = [PageText(1, "a" * 1200)]
        chunks = chunk_pages(pages, chunk_chars=400, overlap_chars=0)
        for c in chunks:
            # cheap est = chars // 4
            assert c.token_estimate == max(1, c.char_count // 4)

    def test_default_constants_used(self):
        # If no kwargs given, we should still produce chunks under defaults.
        pages = [PageText(1, "x" * (DEFAULT_CHUNK_CHARS * 2))]
        chunks = chunk_pages(pages)
        assert len(chunks) > 1
        # First chunk fills exactly the default size.
        assert chunks[0].char_count == DEFAULT_CHUNK_CHARS
        # Step between chunk starts == chunk - overlap
        # (we can't see the cursor directly, but adjacent chunks must overlap by overlap_chars)
        assert chunks[0].text[-DEFAULT_OVERLAP_CHARS:] == chunks[1].text[:DEFAULT_OVERLAP_CHARS]


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------


class TestCosine:
    def test_identical_vectors_score_1(self):
        a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        b = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
        assert pytest.approx(cosine(a, b)[0], abs=1e-6) == 1.0

    def test_orthogonal_vectors_score_0(self):
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([[0.0, 1.0]], dtype=np.float32)
        assert pytest.approx(cosine(a, b)[0], abs=1e-6) == 0.0

    def test_opposite_vectors_score_minus_1(self):
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([[-1.0, 0.0]], dtype=np.float32)
        assert pytest.approx(cosine(a, b)[0], abs=1e-6) == -1.0

    def test_ranking_by_cosine(self):
        # Query points roughly toward [1, 1, 0].
        q = np.array([1.0, 1.0, 0.0], dtype=np.float32)
        docs = np.array(
            [
                [1.0, 1.0, 0.0],   # identical → 1.0
                [1.0, 0.0, 0.0],   # 45° away  → 0.7071
                [0.0, 0.0, 1.0],   # orthogonal → 0
                [-1.0, -1.0, 0.0], # opposite → -1
            ],
            dtype=np.float32,
        )
        scores = cosine(q, docs)
        # Order should be 0 > 1 > 2 > 3
        order = np.argsort(-scores)
        assert order.tolist() == [0, 1, 2, 3]

    def test_empty_matrix_returns_empty(self):
        a = np.array([1.0, 0.0], dtype=np.float32)
        out = cosine(a, np.empty((0, 2), dtype=np.float32))
        assert out.shape == (0,)

    def test_zero_vector_no_division_error(self):
        # A zero embedding shouldn't divide-by-zero; we mask the denominator.
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([[0.0, 0.0]], dtype=np.float32)
        out = cosine(a, b)
        # We don't insist on a particular value, only that it's finite.
        assert np.isfinite(out[0])


# ---------------------------------------------------------------------------
# Retrieval helpers
# ---------------------------------------------------------------------------


class TestSerialise:
    def test_to_dict_round_trip(self):
        rc = RetrievedChunk(
            document_id=1,
            document_title="Reliance FY25 AR",
            document_kind="annual_report",
            document_fy="FY25",
            chunk_idx=42,
            page=47,
            text="management on retail growth: …",
            score=0.87654321,
        )
        d = to_dict(rc)
        assert d["document_id"] == 1
        assert d["document_title"] == "Reliance FY25 AR"
        assert d["page"] == 47
        # Score is rounded to 4 dp
        assert d["score"] == 0.8765

    def test_to_dict_json_safe(self):
        import json

        rc = RetrievedChunk(
            document_id=2,
            document_title="t",
            document_kind="annual_report",
            document_fy=None,
            chunk_idx=0,
            page=None,
            text="x",
            score=0.5,
        )
        # Must not raise
        json.dumps(to_dict(rc))


# ---------------------------------------------------------------------------
# Sanity: Chunk dataclass matches expectations the worker relies on
# ---------------------------------------------------------------------------


def test_chunk_default_pages_spanned_is_empty_tuple():
    c = Chunk(chunk_idx=0, page=1, text="x", char_count=1, token_estimate=1)
    assert c.pages_spanned == ()
