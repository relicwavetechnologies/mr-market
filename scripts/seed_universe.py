"""Seed the `stocks` table with the NIFTY-50 universe.

Idempotent: re-running upserts the rows.
Run from project root: `uv run python -m scripts.seed_universe`
"""

import asyncio
import csv
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert

from app.db.models import Stock
from app.db.session import SessionLocal

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "nifty50.csv"


async def main() -> None:
    rows = []
    with CSV_PATH.open() as f:
        for r in csv.DictReader(f):
            rows.append(
                {
                    "ticker": r["ticker"],
                    "exchange": r["exchange"],
                    "yahoo_symbol": r["yahoo_symbol"],
                    "name": r["name"],
                    "sector": r["sector"] or None,
                    "industry": r["industry"] or None,
                    "active": True,
                }
            )

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
    print(f"Seeded {len(rows)} stocks")


if __name__ == "__main__":
    asyncio.run(main())
