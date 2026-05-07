"""PDF text extraction + chunking.

The chunker is intentionally simple — fixed character window with overlap,
preserving page metadata so the LLM can cite "page 47 of FY25 AR".

Semantic / sentence-aware chunking would be cleaner but adds a dependency
(spaCy / nltk) and the marginal retrieval-quality gain is small at the
size of corpus we're targeting (~10 docs × ~80 chunks).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ~500 tokens at ~4 chars/token. Overlap 50 tokens (~200 chars).
DEFAULT_CHUNK_CHARS = 2000
DEFAULT_OVERLAP_CHARS = 200


@dataclass(slots=True, frozen=True)
class PageText:
    page: int            # 1-based page number for citation
    text: str


@dataclass(slots=True, frozen=True)
class Chunk:
    chunk_idx: int       # 0-based across the whole document
    page: int            # primary page this chunk anchors to
    text: str
    char_count: int
    token_estimate: int  # cheap approximation: chars // 4
    pages_spanned: tuple[int, ...] = field(default_factory=tuple)


def _est_tokens(s: str) -> int:
    return max(1, len(s) // 4)


def extract_pages(path: Path) -> list[PageText]:
    """Extract per-page text from a PDF using pypdf.

    Skips pages that fail to extract — never aborts the whole doc.
    """
    import pypdf

    out: list[PageText] = []
    try:
        reader = pypdf.PdfReader(str(path))
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"could not open PDF {path}: {e}") from e

    for i, p in enumerate(reader.pages, start=1):
        try:
            t = p.extract_text() or ""
        except Exception as e:  # noqa: BLE001
            logger.warning("page %d extract failed: %s", i, e)
            continue
        # Strip NUL bytes (PDFs sometimes embed \x00 — Postgres UTF-8 rejects them).
        # Then collapse runs of whitespace.
        t = t.replace("\x00", "")
        t = " ".join(t.split())
        if t:
            out.append(PageText(page=i, text=t))
    return out


def chunk_pages(
    pages: list[PageText],
    *,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[Chunk]:
    """Concatenate per-page text and slide a fixed-size window.

    For each chunk we record the page where the window *started* (primary
    citation) and every page it touches (so the LLM can hyperlink to a
    range like "pp. 47-49"). Page boundaries are tracked by character
    offsets in the concatenated stream.
    """
    if not pages:
        return []
    if chunk_chars <= 0:
        raise ValueError("chunk_chars must be positive")
    if overlap_chars < 0 or overlap_chars >= chunk_chars:
        raise ValueError("overlap_chars must be in [0, chunk_chars)")

    # Stitch: text + boundary offsets per page.
    boundaries: list[tuple[int, int]] = []   # (start, page)
    parts: list[str] = []
    pos = 0
    for p in pages:
        boundaries.append((pos, p.page))
        parts.append(p.text)
        pos += len(p.text) + 1  # +1 for the join separator below
    full = "\n".join(parts)

    def _page_at(offset: int) -> int:
        # Linear scan — boundaries list is small.
        page = boundaries[0][1]
        for start, p in boundaries:
            if start > offset:
                break
            page = p
        return page

    def _pages_in_span(lo: int, hi: int) -> tuple[int, ...]:
        seen: list[int] = []
        for start, p in boundaries:
            if start >= hi:
                break
            if start >= lo or p == _page_at(lo):
                if not seen or seen[-1] != p:
                    seen.append(p)
        return tuple(seen)

    out: list[Chunk] = []
    step = chunk_chars - overlap_chars
    idx = 0
    cursor = 0
    while cursor < len(full):
        end = min(cursor + chunk_chars, len(full))
        text = full[cursor:end].strip()
        if text:
            out.append(
                Chunk(
                    chunk_idx=idx,
                    page=_page_at(cursor),
                    text=text,
                    char_count=len(text),
                    token_estimate=_est_tokens(text),
                    pages_spanned=_pages_in_span(cursor, end),
                )
            )
            idx += 1
        if end >= len(full):
            break
        cursor += step

    return out
