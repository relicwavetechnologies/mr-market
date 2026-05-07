"""One-shot universe-wide shareholding backfill.

    uv run python -m scripts.backfill_holdings
    uv run python -m scripts.backfill_holdings --tickers RELIANCE TCS
"""

from __future__ import annotations

import argparse
import asyncio

from app.db.session import SessionLocal
from app.workers.holdings_ingest import ingest_for_universe


async def main_async(tickers: list[str] | None) -> None:
    async with SessionLocal() as session:
        results = await ingest_for_universe(session, tickers=tickers, delay_s=0.4)
    ok = sum(1 for r in results if r.error is None)
    print(f"\nDone: {ok}/{len(results)} tickers OK\n")
    for r in results:
        tag = "OK   " if r.error is None else "FAIL "
        print(
            f"  {tag} {r.ticker:<14} fetched={r.fetched:3d} "
            f"upserted={r.upserted:3d} ms={r.duration_ms:5d} {r.error or ''}"
        )


def main() -> None:
    p = argparse.ArgumentParser(description="Backfill NSE shareholding into the holdings table")
    p.add_argument("--tickers", nargs="+", help="restrict to these tickers")
    args = p.parse_args()
    tickers = [t.upper() for t in args.tickers] if args.tickers else None
    asyncio.run(main_async(tickers))


if __name__ == "__main__":
    main()
