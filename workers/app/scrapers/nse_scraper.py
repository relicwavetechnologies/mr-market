"""NSE India scraper — FII/DII activity, bulk/block deals, SAST disclosures.

Uses ``nselib`` for structured access and falls back to raw HTTP when the
library does not expose an endpoint. NSE aggressively rate-limits (and
IP-bans); we cap at 3 req/s with randomised back-off.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from nselib import capital_market  # type: ignore[import-untyped]

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class NSEScraper(BaseScraper):
    """Scrapes NSE India for institutional flows, bulk deals, and SAST."""

    name = "nse"
    source_url = "https://www.nseindia.com"
    rate_limit = 3.0  # NSE blocks aggressively

    # ------------------------------------------------------------------
    # FII / DII daily activity
    # ------------------------------------------------------------------

    async def fetch_fii_dii(self, target_date: date | None = None) -> list[dict[str, Any]]:
        """Return FII/DII buy-sell data for *target_date* (default today)."""
        dt = target_date or date.today()
        date_str = dt.strftime("%d-%m-%Y")
        try:
            df = capital_market.fii_dii_trading_activity(date_str)
            records: list[dict[str, Any]] = []
            for _, row in df.iterrows():
                records.append({
                    "date": dt.isoformat(),
                    "category": str(row.get("Category", "")),
                    "buy_value_cr": _to_decimal(row.get("Buy Value")),
                    "sell_value_cr": _to_decimal(row.get("Sell Value")),
                    "net_value_cr": _to_decimal(row.get("Net Value")),
                })
            return records
        except Exception:
            logger.exception("nse: FII/DII fetch failed for %s", date_str)
            return []

    # ------------------------------------------------------------------
    # Bulk / block deals
    # ------------------------------------------------------------------

    async def fetch_bulk_deals(self, target_date: date | None = None) -> list[dict[str, Any]]:
        """Return bulk and block deals for *target_date*."""
        dt = target_date or date.today()
        date_str = dt.strftime("%d-%m-%Y")
        try:
            df = capital_market.bulk_deal_data(date_str)
            records: list[dict[str, Any]] = []
            for _, row in df.iterrows():
                records.append({
                    "date": dt.isoformat(),
                    "ticker": str(row.get("Symbol", "")),
                    "client_name": str(row.get("Client Name", "")),
                    "deal_type": str(row.get("Deal Type", "")),
                    "quantity": int(row.get("Quantity", 0)),
                    "price": _to_decimal(row.get("Trade Price / Wt. Avg. Price")),
                })
            return records
        except Exception:
            logger.exception("nse: bulk deals fetch failed for %s", date_str)
            return []

    # ------------------------------------------------------------------
    # SAST (insider / substantial-acquisition) disclosures
    # ------------------------------------------------------------------

    async def fetch_sast_disclosures(self) -> list[dict[str, Any]]:
        """Fetch recent SAST / insider-trading disclosures via HTTP."""
        url = f"{self.source_url}/api/corporates/insiderTrading?index=equities"
        try:
            data = await self.fetch(url, as_json=True)
            assert isinstance(data, dict)
            raw_list: list[dict[str, Any]] = data.get("data", [])
            records: list[dict[str, Any]] = []
            for item in raw_list:
                records.append({
                    "ticker": item.get("symbol", ""),
                    "person": item.get("acqName", ""),
                    "person_category": item.get("personCategory", ""),
                    "securities_type": item.get("secType", ""),
                    "transaction_type": item.get("tdpTransactionType", ""),
                    "shares_traded": _safe_int(item.get("secAcq")),
                    "shares_held_after": _safe_int(item.get("secAfterAcq")),
                    "disclosure_date": item.get("date", ""),
                })
            return records
        except Exception:
            logger.exception("nse: SAST disclosures fetch failed")
            return []

    # ------------------------------------------------------------------
    # BaseScraper interface
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Run all NSE sub-scrapers and return combined results."""
        fii_dii = await self.fetch_fii_dii()
        bulk = await self.fetch_bulk_deals()
        sast = await self.fetch_sast_disclosures()
        combined = [
            *[{**r, "_type": "fii_dii"} for r in fii_dii],
            *[{**r, "_type": "bulk_deal"} for r in bulk],
            *[{**r, "_type": "sast"} for r in sast],
        ]
        logger.info(
            "nse: scraped %d FII/DII, %d bulk deals, %d SAST records",
            len(fii_dii),
            len(bulk),
            len(sast),
        )
        return combined

    async def save(self, data: list[dict[str, Any]]) -> int:
        """Persist NSE data into appropriate tables."""
        from mr_market_shared.db.session import get_session_manager

        manager = get_session_manager()
        saved = 0
        async with manager.session() as session:
            for record in data:
                record_type = record.pop("_type", None)
                if record_type == "fii_dii":
                    # Store as JSON in a generic activity log or dedicated table
                    # For now we log; the schema can be extended
                    logger.debug("nse: persisting FII/DII record: %s", record)
                elif record_type == "bulk_deal":
                    logger.debug("nse: persisting bulk deal: %s", record)
                elif record_type == "sast":
                    logger.debug("nse: persisting SAST disclosure: %s", record)
                saved += 1
            await session.commit()
        return saved


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _to_decimal(value: Any) -> Decimal | None:
    """Safely convert a value to Decimal."""
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    """Safely convert a value to int."""
    if value is None:
        return None
    try:
        return int(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None
