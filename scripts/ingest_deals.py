"""One-shot ingest for NSE bulk + block deals.

    uv run python -m scripts.ingest_deals                        # both, period=1M
    uv run python -m scripts.ingest_deals --kind bulk --period 3M
    uv run python -m scripts.ingest_deals --kind block --period 1Y
"""

from __future__ import annotations

import argparse
import asyncio

from app.db.session import SessionLocal
from app.workers.deals_ingest import ingest_both, ingest_deals


async def main_async(kind: str, period: str) -> None:
    async with SessionLocal() as session:
        if kind == "all":
            results = await ingest_both(session, period=period)
        else:
            results = [await ingest_deals(session, kind=kind, period=period)]  # type: ignore[arg-type]

    for s in results:
        tag = "OK   " if s.error is None else "FAIL "
        print(
            f"  {tag} {s.kind:<5} period={s.period:<3} "
            f"fetched={s.fetched:5d} matched={s.matched_universe:4d} "
            f"upserted={s.upserted:4d} ms={s.duration_ms:5d} "
            f"{s.error or ''}"
        )


def main() -> None:
    p = argparse.ArgumentParser(description="Ingest NSE bulk + block deals")
    p.add_argument(
        "--kind", choices=["bulk", "block", "all"], default="all",
        help="which kind to ingest (default: both)",
    )
    p.add_argument(
        "--period", default="1M",
        help="nselib period: 1D / 1W / 1M / 3M / 6M / 1Y (default 1M)",
    )
    args = p.parse_args()
    asyncio.run(main_async(args.kind, args.period))


if __name__ == "__main__":
    main()
