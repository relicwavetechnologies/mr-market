"""Seed the `stocks` table with the configured universe.

Idempotent: re-running upserts the rows. Phase-3 default universe is
NIFTY-100 (NIFTY 50 + NIFTY Next 50). The legacy NIFTY-50 file is still
shipped for ops that need the smaller universe (e.g. backfill rate-limit
fallback).

Usage::

    # Default — NIFTY 100
    uv run python -m scripts.seed_universe

    # Force the smaller universe
    uv run python -m scripts.seed_universe --universe nifty50

    # Or load from an arbitrary CSV in the same shape
    uv run python -m scripts.seed_universe --csv path/to/custom.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert

from app.db.models import Stock
from app.db.session import SessionLocal

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Allow `--universe nifty100` (default) or `--universe nifty50`.
UNIVERSES = {
    "nifty50": DATA_DIR / "nifty50.csv",
    "nifty100": DATA_DIR / "nifty100.csv",
}


def parse_csv(path: Path) -> list[dict]:
    """Read a universe CSV. Pure-functional so unit tests can hit it
    without touching Postgres."""
    rows: list[dict] = []
    with path.open() as f:
        for r in csv.DictReader(f):
            rows.append(
                {
                    "ticker": r["ticker"].strip(),
                    "exchange": r["exchange"].strip(),
                    "yahoo_symbol": (r.get("yahoo_symbol") or "").strip() or None,
                    "name": r["name"].strip(),
                    "sector": (r.get("sector") or "").strip() or None,
                    "industry": (r.get("industry") or "").strip() or None,
                    "active": True,
                }
            )
    return rows


async def seed(rows: list[dict]) -> int:
    """Upsert universe rows. Returns the number of rows touched."""
    if not rows:
        return 0
    async with SessionLocal() as session:
        stmt = insert(Stock).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Stock.ticker],
            set_={
                "exchange": stmt.excluded.exchange,
                "yahoo_symbol": stmt.excluded.yahoo_symbol,
                "name": stmt.excluded.name,
                "sector": stmt.excluded.sector,
                "industry": stmt.excluded.industry,
                "active": stmt.excluded.active,
            },
        )
        await session.execute(stmt)
        await session.commit()
    return len(rows)


async def main_async(args: argparse.Namespace) -> None:
    if args.csv:
        path = Path(args.csv)
    else:
        try:
            path = UNIVERSES[args.universe]
        except KeyError:
            raise SystemExit(
                f"Unknown universe {args.universe!r}; expected one of "
                f"{sorted(UNIVERSES)} or pass --csv <path>."
            )
    if not path.exists():
        raise SystemExit(f"Universe file not found: {path}")

    rows = parse_csv(path)
    n = await seed(rows)
    print(f"Seeded {n} stocks from {path.name}")


def main() -> None:
    p = argparse.ArgumentParser(description="Seed the stocks universe")
    p.add_argument(
        "--universe",
        default="nifty100",
        choices=sorted(UNIVERSES),
        help="named universe to seed (default: nifty100)",
    )
    p.add_argument(
        "--csv",
        help="path to a custom universe CSV — overrides --universe",
    )
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
