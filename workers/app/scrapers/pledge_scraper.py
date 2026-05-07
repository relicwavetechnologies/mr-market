"""NSE pledge disclosure scraper — promoter pledge percentages.

Monitors promoter pledge data from NSE disclosures. A promoter pledge
above 10% is flagged as a red flag — it indicates the promoter has
pledged significant equity as collateral, which can trigger forced
selling if the stock drops.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Pledge red-flag threshold (percentage)
PLEDGE_RED_FLAG_THRESHOLD = Decimal("10.0")


class PledgeScraper(BaseScraper):
    """Scrapes NSE for promoter pledge disclosures and flags high-risk pledges."""

    name = "pledge"
    source_url = "https://www.nseindia.com"
    rate_limit = 3.0  # Same as NSE scraper — shared rate limit window

    # ------------------------------------------------------------------
    # Pledge data fetching
    # ------------------------------------------------------------------

    async def fetch_pledge_data(self, ticker: str) -> dict[str, Any] | None:
        """Fetch promoter pledge data for a single *ticker* from NSE.

        Returns a dict with pledge percentage and red-flag status.
        """
        url = (
            f"{self.source_url}/api/corporates/pledgedetails"
            f"?index=equities&symbol={ticker}"
        )
        try:
            data = await self.fetch(url, as_json=True)
            assert isinstance(data, dict)
            return self._parse_pledge_response(data, ticker)
        except Exception:
            logger.exception("pledge: fetch failed for %s", ticker)
            return None

    def _parse_pledge_response(
        self,
        data: dict[str, Any],
        ticker: str,
    ) -> dict[str, Any]:
        """Parse NSE pledge API response into structured data."""
        records = data.get("data", [])
        if not records:
            return {
                "ticker": ticker,
                "promoter_pledge_pct": None,
                "is_red_flag": False,
                "details": [],
            }

        # Take the most recent disclosure
        latest = records[0]
        total_shares = _safe_decimal(latest.get("totProShares"))
        pledged_shares = _safe_decimal(latest.get("totProSharesPledged"))

        pledge_pct: Decimal | None = None
        if total_shares and total_shares > 0:
            pledge_pct = (pledged_shares or Decimal("0")) / total_shares * 100

        is_red_flag = pledge_pct is not None and pledge_pct > PLEDGE_RED_FLAG_THRESHOLD

        # Build detail records for all promoter entities
        details: list[dict[str, Any]] = []
        for entity in latest.get("pledgeDetails", records):
            details.append({
                "entity_name": entity.get("promoterName", ""),
                "total_shares": _safe_int(entity.get("totProShares")),
                "pledged_shares": _safe_int(entity.get("totProSharesPledged")),
                "pledge_pct": str(pledge_pct) if pledge_pct else None,
            })

        result = {
            "ticker": ticker,
            "promoter_pledge_pct": str(pledge_pct) if pledge_pct else None,
            "is_red_flag": is_red_flag,
            "disclosure_date": latest.get("date", date.today().isoformat()),
            "details": details,
        }

        if is_red_flag:
            logger.warning(
                "pledge: RED FLAG — %s has %.1f%% promoter shares pledged",
                ticker,
                pledge_pct,
            )

        return result

    # ------------------------------------------------------------------
    # Batch scanning
    # ------------------------------------------------------------------

    async def scan_universe(self, tickers: list[str]) -> list[dict[str, Any]]:
        """Scan all tickers in the universe for pledge data.

        Returns records sorted by pledge percentage (highest first).
        """
        results: list[dict[str, Any]] = []
        for ticker in tickers:
            data = await self.fetch_pledge_data(ticker)
            if data:
                results.append(data)

        # Sort by pledge percentage, descending — red flags first
        results.sort(
            key=lambda r: Decimal(r["promoter_pledge_pct"] or "0"),
            reverse=True,
        )
        red_flags = [r for r in results if r.get("is_red_flag")]
        logger.info(
            "pledge: scanned %d tickers, %d red flags (>%.0f%% pledged)",
            len(tickers),
            len(red_flags),
            PLEDGE_RED_FLAG_THRESHOLD,
        )
        return results

    # ------------------------------------------------------------------
    # BaseScraper interface
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Default scrape — call :meth:`scan_universe` with ticker list."""
        logger.info("pledge: use scan_universe() with a ticker list")
        return []

    async def save(self, data: list[dict[str, Any]]) -> int:
        """Persist pledge data into the shareholding table."""
        from mr_market_shared.db.session import get_session_manager

        manager = get_session_manager()
        saved = 0
        async with manager.session() as session:
            for record in data:
                # Update the promoter_pledge_pct field in Shareholding
                from mr_market_shared.db.models import Shareholding
                from sqlalchemy import update

                ticker = record["ticker"]
                pledge_pct = record.get("promoter_pledge_pct")
                if pledge_pct is not None:
                    stmt = (
                        update(Shareholding)
                        .where(Shareholding.ticker == ticker)
                        .values(promoter_pledge_pct=Decimal(pledge_pct))
                    )
                    await session.execute(stmt)
                    saved += 1
            await session.commit()
        logger.info("pledge: updated %d shareholding records", saved)
        return saved


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _safe_decimal(value: Any) -> Decimal | None:
    """Safely convert to Decimal."""
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    """Safely convert to int."""
    if value is None:
        return None
    try:
        return int(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None
