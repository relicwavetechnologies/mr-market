"""One-shot research-document (PDF) ingest.

    uv run python -m scripts.ingest_research \
        --ticker RELIANCE \
        --pdf data/annual_reports/RELIANCE_FY25.pdf \
        --title "Reliance Industries Integrated Annual Report 2024-25" \
        --fy FY25

Run again with the same (ticker, kind, fy) to replace the chunks
(idempotent re-ingest).
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from redis import asyncio as aioredis

from app.config import get_settings
from app.db.session import SessionLocal
from app.workers.research_ingest import ingest_pdf


async def main_async(
    ticker: str,
    pdf: Path,
    title: str,
    *,
    kind: str,
    fy: str | None,
    source_url: str | None,
) -> None:
    settings = get_settings()
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        async with SessionLocal() as session:
            stats = await ingest_pdf(
                session,
                ticker=ticker,
                pdf_path=pdf,
                title=title,
                kind=kind,
                fy=fy,
                source_url=source_url,
                redis=redis,
            )
    finally:
        try:
            await redis.aclose()
        except Exception:  # noqa: BLE001
            pass

    tag = "OK" if stats.error is None else "FAIL"
    print(
        f"\n[{tag}] {ticker} {kind} {fy or ''}\n"
        f"  pages: {stats.n_pages}\n"
        f"  chunks: {stats.n_chunks}\n"
        f"  embedded: {stats.n_embedded}\n"
        f"  duration: {stats.duration_ms} ms\n"
        f"  error: {stats.error or '—'}\n"
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Ingest a research PDF into the RAG corpus")
    p.add_argument("--ticker", required=True, help="NSE ticker (RELIANCE / TCS / INFY / ...)")
    p.add_argument("--pdf", required=True, type=Path, help="path to the PDF file")
    p.add_argument("--title", required=True, help="human title")
    p.add_argument(
        "--kind", default="annual_report",
        choices=["annual_report", "concall_transcript", "research_note", "other"],
    )
    p.add_argument("--fy", help="fiscal-year tag, e.g. FY25")
    p.add_argument("--source-url", help="canonical URL where this PDF lives")
    args = p.parse_args()
    asyncio.run(
        main_async(
            args.ticker.upper(),
            args.pdf,
            args.title,
            kind=args.kind,
            fy=args.fy,
            source_url=args.source_url,
        )
    )


if __name__ == "__main__":
    main()
