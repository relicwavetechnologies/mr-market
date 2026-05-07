"""Screener.in scraper — fundamental data with yfinance cross-validation.

Screener.in is the primary source for Indian stock fundamentals. We scrape
individual stock pages for P/E, ROE, ROCE, D/E, and growth ratios, then
cross-validate key metrics against yfinance data for confidence scoring.

Rate limit: 30 req/min (0.5 req/s). Exceeding this triggers IP bans.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

import yfinance as yf  # type: ignore[import-untyped]
from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class ScreenerScraper(BaseScraper):
    """Scrapes Screener.in for stock fundamentals with yfinance fallback."""

    name = "screener"
    source_url = "https://www.screener.in"
    rate_limit = 0.5  # 30 req/min

    # Tolerance for cross-validation (percentage difference)
    CROSS_VALIDATION_TOLERANCE = 0.15  # 15%

    # ------------------------------------------------------------------
    # Fundamentals scraping
    # ------------------------------------------------------------------

    async def fetch_fundamentals(self, ticker: str) -> dict[str, Any]:
        """Scrape fundamental data for *ticker* from Screener.in.

        Returns a dict compatible with the ``Fundamental`` ORM model.
        """
        # Screener uses company slugs; NSE tickers map 1:1 for most stocks
        url = f"{self.source_url}/company/{ticker}/consolidated/"
        try:
            html = await self.fetch(url)
            assert isinstance(html, str)
            data = self._parse_fundamentals(html, ticker)
            return data
        except Exception:
            logger.warning("screener: primary fetch failed for %s, trying standalone", ticker)
            # Retry with standalone URL
            url_standalone = f"{self.source_url}/company/{ticker}/"
            try:
                html = await self.fetch(url_standalone)
                assert isinstance(html, str)
                return self._parse_fundamentals(html, ticker)
            except Exception:
                logger.exception("screener: all fetches failed for %s", ticker)
                return {"ticker": ticker, "error": True}

    def _parse_fundamentals(self, html: str, ticker: str) -> dict[str, Any]:
        """Parse fundamental ratios from Screener.in HTML."""
        soup = BeautifulSoup(html, "lxml")
        data: dict[str, Any] = {"ticker": ticker, "scraped_date": date.today().isoformat()}

        # Screener uses a <ul> with id="top-ratios" for key metrics
        ratios_section = soup.find("ul", {"id": "top-ratios"})
        if ratios_section:
            items = ratios_section.find_all("li")
            for item in items:
                name_el = item.find("span", class_="name")
                value_el = item.find("span", class_="number")
                if not name_el or not value_el:
                    continue
                name = name_el.get_text(strip=True).lower()
                value = _parse_number(value_el.get_text(strip=True))

                if "market cap" in name:
                    data["market_cap"] = value
                elif "stock p/e" in name or "current price" not in name and "p/e" in name:
                    data["pe"] = value
                elif "industry p/e" in name:
                    data["pe_industry"] = value
                elif "book value" in name:
                    data["book_value"] = value
                elif "dividend yield" in name:
                    data["dividend_yield_pct"] = value
                elif "roce" in name:
                    data["roce"] = value
                elif "roe" in name:
                    data["roe"] = value
                elif "face value" in name:
                    pass  # not stored

        # Parse the key ratios table for D/E, EPS, growth
        ratios_table = soup.find("section", {"id": "ratios"})
        if ratios_table:
            for row in ratios_table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                label = cells[0].get_text(strip=True).lower()
                # Take the most recent column value
                recent_value = _parse_number(cells[-1].get_text(strip=True))

                if "debt to equity" in label or "debt / equity" in label:
                    data["debt_equity"] = recent_value
                elif "eps" in label and "diluted" not in label:
                    data["eps"] = recent_value
                elif "revenue growth" in label or "sales growth" in label:
                    data["revenue_growth_pct"] = recent_value
                elif "profit growth" in label or "net profit growth" in label:
                    data["profit_growth_pct"] = recent_value
                elif "price to book" in label or "p/b" in label:
                    data["pb"] = recent_value

        return data

    # ------------------------------------------------------------------
    # Cross-validation with yfinance
    # ------------------------------------------------------------------

    async def cross_validate(self, ticker: str, screener_data: dict[str, Any]) -> str:
        """Cross-validate Screener data against yfinance.

        Returns confidence level: ``"HIGH"``, ``"MEDIUM"``, or ``"LOW"``.
        """
        yf_ticker = f"{ticker}.NS"  # NSE suffix for yfinance
        try:
            stock = yf.Ticker(yf_ticker)
            info = stock.info or {}
        except Exception:
            logger.warning("screener: yfinance cross-validation failed for %s", ticker)
            return "MEDIUM"  # can't validate, assume moderate confidence

        matches = 0
        checks = 0

        # Compare P/E
        yf_pe = info.get("trailingPE")
        sc_pe = screener_data.get("pe")
        if yf_pe and sc_pe:
            checks += 1
            if _within_tolerance(float(sc_pe), float(yf_pe), self.CROSS_VALIDATION_TOLERANCE):
                matches += 1

        # Compare Market Cap (in Cr)
        yf_mcap = info.get("marketCap")
        sc_mcap = screener_data.get("market_cap")
        if yf_mcap and sc_mcap:
            checks += 1
            yf_mcap_cr = yf_mcap / 1e7  # Convert to crores
            if _within_tolerance(float(sc_mcap), yf_mcap_cr, self.CROSS_VALIDATION_TOLERANCE):
                matches += 1

        # Compare ROE
        yf_roe = info.get("returnOnEquity")
        sc_roe = screener_data.get("roe")
        if yf_roe and sc_roe:
            checks += 1
            yf_roe_pct = yf_roe * 100
            if _within_tolerance(float(sc_roe), yf_roe_pct, self.CROSS_VALIDATION_TOLERANCE):
                matches += 1

        if checks == 0:
            return "LOW"
        ratio = matches / checks
        if ratio >= 0.8:
            return "HIGH"
        if ratio >= 0.5:
            return "MEDIUM"
        return "LOW"

    # ------------------------------------------------------------------
    # Batch scrape for universe
    # ------------------------------------------------------------------

    async def scrape_universe(self, tickers: list[str]) -> list[dict[str, Any]]:
        """Scrape fundamentals for a list of tickers with cross-validation."""
        results: list[dict[str, Any]] = []
        for ticker in tickers:
            data = await self.fetch_fundamentals(ticker)
            if data.get("error"):
                logger.warning("screener: skipping %s due to fetch error", ticker)
                continue
            confidence = await self.cross_validate(ticker, data)
            data["confidence"] = confidence
            data.pop("error", None)
            results.append(data)
        return results

    # ------------------------------------------------------------------
    # BaseScraper interface
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Default scrape — requires tickers to be set externally.

        For batch operation, call :meth:`scrape_universe` directly with
        a ticker list.
        """
        logger.info("screener: use scrape_universe() for batch scraping")
        return []

    async def save(self, data: list[dict[str, Any]]) -> int:
        """Persist fundamentals to the database."""
        from mr_market_shared.db.models import Fundamental
        from mr_market_shared.db.session import get_session_manager

        manager = get_session_manager()
        saved = 0
        async with manager.session() as session:
            for record in data:
                fundamental = Fundamental(
                    ticker=record["ticker"],
                    scraped_date=date.fromisoformat(record["scraped_date"]),
                    market_cap=_to_decimal(record.get("market_cap")),
                    pe=_to_decimal(record.get("pe")),
                    pe_industry=_to_decimal(record.get("pe_industry")),
                    pb=_to_decimal(record.get("pb")),
                    roe=_to_decimal(record.get("roe")),
                    roce=_to_decimal(record.get("roce")),
                    debt_equity=_to_decimal(record.get("debt_equity")),
                    revenue_growth_pct=_to_decimal(record.get("revenue_growth_pct")),
                    profit_growth_pct=_to_decimal(record.get("profit_growth_pct")),
                    dividend_yield_pct=_to_decimal(record.get("dividend_yield_pct")),
                    eps=_to_decimal(record.get("eps")),
                    book_value=_to_decimal(record.get("book_value")),
                    confidence=record.get("confidence"),
                )
                session.add(fundamental)
                saved += 1
            await session.commit()
        return saved


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _parse_number(text: str) -> Decimal | None:
    """Parse a number string like '1,234.56' or '23.4%' to Decimal."""
    cleaned = text.replace(",", "").replace("%", "").replace("Cr.", "").strip()
    if not cleaned or cleaned == "-":
        return None
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def _to_decimal(value: Any) -> Decimal | None:
    """Convert any value to Decimal, or None."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _within_tolerance(a: float, b: float, tolerance: float) -> bool:
    """Check if two values are within *tolerance* % of each other."""
    if b == 0:
        return a == 0
    return abs(a - b) / abs(b) <= tolerance
