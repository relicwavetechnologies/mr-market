"""One-shot technicals compute over the universe.

    uv run python -m scripts.compute_technicals
    uv run python -m scripts.compute_technicals --tickers RELIANCE TCS INFY
    uv run python -m scripts.compute_technicals --lookback 365
"""

from __future__ import annotations

import argparse
import asyncio

from app.db.session import SessionLocal
from app.workers.technicals_compute import (
    DEFAULT_LOOKBACK_DAYS,
    compute_for_universe,
)


async def main_async(tickers: list[str] | None, lookback: int) -> None:
    async with SessionLocal() as session:
        results = await compute_for_universe(
            session, tickers=tickers, lookback_days=lookback
        )
    ok = sum(1 for r in results if r.error is None)
    print(f"\nDone: {ok}/{len(results)} tickers OK\n")
    for r in results:
        tag = "OK   " if r.error is None else "FAIL "
        print(
            f"  {tag} {r.ticker:<14} rows_in={r.rows_in:4d} out={r.rows_out:4d} "
            f"rsi_n={r.rows_with_rsi:4d} sma200_n={r.rows_with_sma200:4d} "
            f"ms={r.duration_ms:5d} {r.error or ''}"
        )


def main() -> None:
    p = argparse.ArgumentParser(description="Compute technicals into the technicals table")
    p.add_argument("--tickers", nargs="+", help="restrict to these tickers")
    p.add_argument(
        "--lookback",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help=f"lookback days (default {DEFAULT_LOOKBACK_DAYS})",
    )
    args = p.parse_args()
    tickers = [t.upper() for t in args.tickers] if args.tickers else None
    asyncio.run(main_async(tickers, args.lookback))


if __name__ == "__main__":
    main()
