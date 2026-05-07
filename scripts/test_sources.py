"""Standalone source health check.

Hits each quote source for one ticker and prints the result. Use this to verify
real-data connectivity before running the full /quote endpoint.

    uv run python -m scripts.test_sources RELIANCE
"""

from __future__ import annotations

import asyncio
import sys

from app.data.sources import moneycontrol as mc_src
from app.data.sources import nse as nse_src
from app.data.sources import screener as scr_src
from app.data.sources import yf as yf_src
from app.data.types import QuoteSourceError

SOURCES = {
    "yfinance": yf_src.fetch,
    "nselib": nse_src.fetch,
    "screener": scr_src.fetch,
    "moneycontrol": mc_src.fetch,
}


async def main() -> None:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"
    print(f"Testing sources for {ticker}\n")

    async def _one(name, fn):
        try:
            q = await fn(ticker)
            return name, q, None
        except QuoteSourceError as e:
            return name, None, str(e)
        except Exception as e:  # noqa: BLE001
            return name, None, f"unexpected: {e!s}"

    results = await asyncio.gather(*[_one(n, fn) for n, fn in SOURCES.items()])
    for name, q, err in results:
        if q is not None:
            print(
                f"  OK    {name:14s}  ₹{q.price}"
                f"   prev_close={q.prev_close}"
                f"   open={q.day_open}  high={q.day_high}  low={q.day_low}"
            )
        else:
            print(f"  FAIL  {name:14s}  {err}")


if __name__ == "__main__":
    asyncio.run(main())
