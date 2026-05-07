"""One-shot EOD backfill from `nsearchives.nseindia.com`.

    uv run python -m scripts.backfill_eod --days 30
    uv run python -m scripts.backfill_eod --days 7 --end 2026-05-06
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date

from app.db.session import SessionLocal
from app.workers.eod_ingest import backfill


async def main_async(days: int, end: date | None) -> None:
    async with SessionLocal() as session:
        results = await backfill(session, days=days, end=end)

    ok = sum(1 for r in results if r.error is None)
    print(f"\nDone: {ok}/{len(results)} dates ingested OK\n")
    for r in results:
        tag = "OK  " if r.error is None else "MISS"
        print(
            f"  {tag}  {r.trade_date}  fetched={r.fetched:4d}  "
            f"upserted={r.upserted:4d}  ms={r.duration_ms:5d}  "
            f"{r.error or ''}"
        )


def main() -> None:
    p = argparse.ArgumentParser(description="Backfill EOD bhavcopy from NSE archive")
    p.add_argument("--days", type=int, default=30, help="number of calendar days to walk back")
    p.add_argument("--end", type=str, help="end date YYYY-MM-DD (default = today IST)")
    args = p.parse_args()
    end = date.fromisoformat(args.end) if args.end else None
    asyncio.run(main_async(args.days, end))


if __name__ == "__main__":
    main()
