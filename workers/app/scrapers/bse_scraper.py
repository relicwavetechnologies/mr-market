"""BSE India scraper — announcements, corporate actions, shareholding patterns.

Uses httpx + BeautifulSoup against BSE's public web pages and JSON APIs.
Rate limit: 5 req/s (BSE is less aggressive than NSE).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class BSEScraper(BaseScraper):
    """Scrapes BSE India for announcements and shareholding patterns."""

    name = "bse"
    source_url = "https://www.bseindia.com"
    rate_limit = 5.0

    # ------------------------------------------------------------------
    # Announcements & corporate actions
    # ------------------------------------------------------------------

    async def fetch_announcements(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch recent corporate announcements from BSE.

        Uses BSE's JSON API endpoint for announcements filtered by date.
        """
        today = date.today()
        from_dt = from_date or today
        to_dt = to_date or today
        url = (
            f"{self.source_url}/corporates/ann.html"
            f"?curpg=1&annession=Latest&dtfrom={from_dt:%d/%m/%Y}"
            f"&dtto={to_dt:%d/%m/%Y}&category=Corp.+Action"
        )
        try:
            html = await self.fetch(url)
            assert isinstance(html, str)
            return self._parse_announcements_html(html)
        except Exception:
            logger.exception("bse: announcements fetch failed")
            return []

    def _parse_announcements_html(self, html: str) -> list[dict[str, Any]]:
        """Parse announcements from BSE HTML response."""
        soup = BeautifulSoup(html, "lxml")
        records: list[dict[str, Any]] = []

        table = soup.find("table", {"id": "ctl00_ContentPlaceHolder1_gvData"})
        if not table:
            # Try alternate layout
            rows = soup.select("tr.TTRow, tr.TTRow_Right")
        else:
            rows = table.find_all("tr")[1:]  # skip header

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 5:
                continue
            records.append({
                "bse_code": cells[0].get_text(strip=True),
                "company_name": cells[1].get_text(strip=True),
                "subject": cells[2].get_text(strip=True),
                "category": cells[3].get_text(strip=True),
                "date": cells[4].get_text(strip=True),
                "source": "bse",
            })
        return records

    # ------------------------------------------------------------------
    # Shareholding patterns (quarterly)
    # ------------------------------------------------------------------

    async def fetch_shareholding(self, bse_code: str, quarter: str) -> dict[str, Any] | None:
        """Fetch shareholding pattern for a stock from BSE.

        Parameters
        ----------
        bse_code:
            BSE scrip code (e.g. ``"500325"`` for Reliance).
        quarter:
            Quarter string (e.g. ``"Q1-2026"``). Mapped to BSE's
            internal quarter representation.
        """
        url = (
            f"{self.source_url}/corporates/shpSecuritywise.html"
            f"?scripcd={bse_code}"
        )
        try:
            html = await self.fetch(url)
            assert isinstance(html, str)
            return self._parse_shareholding_html(html, bse_code, quarter)
        except Exception:
            logger.exception("bse: shareholding fetch failed for %s", bse_code)
            return None

    def _parse_shareholding_html(
        self,
        html: str,
        bse_code: str,
        quarter: str,
    ) -> dict[str, Any]:
        """Extract shareholding percentages from BSE HTML."""
        soup = BeautifulSoup(html, "lxml")
        result: dict[str, Any] = {
            "bse_code": bse_code,
            "quarter": quarter,
            "promoter_pct": None,
            "promoter_pledge_pct": None,
            "fii_pct": None,
            "dii_pct": None,
            "retail_pct": None,
        }

        # BSE presents data in nested tables — extract by known row labels
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            label = cells[0].get_text(strip=True).lower()
            value_text = cells[-1].get_text(strip=True)
            value = _parse_pct(value_text)

            if "promoter" in label and "pledge" not in label and "group" not in label:
                result["promoter_pct"] = value
            elif "pledge" in label:
                result["promoter_pledge_pct"] = value
            elif "foreign" in label and "institutional" in label:
                result["fii_pct"] = value
            elif ("domestic" in label or "mutual" in label) and "institutional" in label:
                result["dii_pct"] = value
            elif "public" in label or "retail" in label:
                result["retail_pct"] = value

        return result

    # ------------------------------------------------------------------
    # BaseScraper interface
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Run BSE scrapers and return combined results."""
        announcements = await self.fetch_announcements()
        logger.info("bse: scraped %d announcements", len(announcements))
        return announcements

    async def save(self, data: list[dict[str, Any]]) -> int:
        """Persist BSE data. Announcements stored in news table as source=bse."""
        from mr_market_shared.db.models import News
        from mr_market_shared.db.session import get_session_manager

        manager = get_session_manager()
        saved = 0
        async with manager.session() as session:
            for record in data:
                news = News(
                    ticker=record.get("bse_code"),
                    headline=record.get("subject"),
                    source="bse",
                    published_at=datetime.now(),
                )
                session.add(news)
                saved += 1
            await session.commit()
        return saved


def _parse_pct(text: str) -> Decimal | None:
    """Parse a percentage string like '62.14%' into Decimal."""
    cleaned = text.replace("%", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except Exception:
        return None
