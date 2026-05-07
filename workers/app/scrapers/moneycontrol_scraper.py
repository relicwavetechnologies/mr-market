"""Moneycontrol scraper — news articles and backup company financials.

Scrapes Moneycontrol for the latest financial news and company-level
financials as a secondary source. Rate limit: 20 req/min.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Mapping of broad Moneycontrol news categories to scrape
_NEWS_CATEGORIES: dict[str, str] = {
    "market": "https://www.moneycontrol.com/news/business/markets/",
    "stocks": "https://www.moneycontrol.com/news/business/stocks/",
    "economy": "https://www.moneycontrol.com/news/business/economy/",
    "ipo": "https://www.moneycontrol.com/news/business/ipo/",
}


class MoneycontrolScraper(BaseScraper):
    """Scrapes Moneycontrol for financial news and company financials."""

    name = "moneycontrol"
    source_url = "https://www.moneycontrol.com"
    rate_limit = 0.333  # 20 req/min

    # ------------------------------------------------------------------
    # News scraping
    # ------------------------------------------------------------------

    async def fetch_news(
        self,
        categories: list[str] | None = None,
        max_articles_per_category: int = 20,
    ) -> list[dict[str, Any]]:
        """Fetch recent news articles from Moneycontrol.

        Parameters
        ----------
        categories:
            News categories to scrape (default: all).
        max_articles_per_category:
            Maximum number of articles to parse per category page.
        """
        target_categories = categories or list(_NEWS_CATEGORIES.keys())
        all_articles: list[dict[str, Any]] = []

        for category in target_categories:
            url = _NEWS_CATEGORIES.get(category)
            if not url:
                logger.warning("moneycontrol: unknown category %r", category)
                continue
            try:
                html = await self.fetch(url)
                assert isinstance(html, str)
                articles = self._parse_news_listing(html, category, max_articles_per_category)
                all_articles.extend(articles)
            except Exception:
                logger.exception("moneycontrol: news fetch failed for category %s", category)

        return all_articles

    def _parse_news_listing(
        self,
        html: str,
        category: str,
        max_articles: int,
    ) -> list[dict[str, Any]]:
        """Parse a Moneycontrol news listing page."""
        soup = BeautifulSoup(html, "lxml")
        articles: list[dict[str, Any]] = []

        # Moneycontrol uses <li> elements inside a news list container
        news_items = soup.select("li.clearfix")[:max_articles]
        for item in news_items:
            headline_tag = item.find("h2") or item.find("h3")
            if not headline_tag:
                continue

            link_tag = headline_tag.find("a")
            headline = headline_tag.get_text(strip=True)
            url = link_tag["href"] if link_tag and link_tag.get("href") else None

            # Extract publication date if available
            date_tag = item.find("span", class_="date") or item.find("p", class_="date")
            published_at = date_tag.get_text(strip=True) if date_tag else None

            articles.append({
                "headline": headline,
                "url": url,
                "category": category,
                "published_at": published_at,
                "source": "moneycontrol",
            })

        return articles

    # ------------------------------------------------------------------
    # Company financials (backup source)
    # ------------------------------------------------------------------

    async def fetch_company_financials(self, mc_slug: str) -> dict[str, Any]:
        """Fetch company financials page as backup data source.

        Parameters
        ----------
        mc_slug:
            Moneycontrol company slug (e.g. ``"RI"`` for Reliance,
            ``"TCS"`` for TCS). The full URL is constructed automatically.
        """
        url = f"{self.source_url}/financials/{mc_slug}/ratiosVI/{mc_slug}"
        try:
            html = await self.fetch(url)
            assert isinstance(html, str)
            return self._parse_financials(html, mc_slug)
        except Exception:
            logger.exception("moneycontrol: financials fetch failed for %s", mc_slug)
            return {"slug": mc_slug, "error": True}

    def _parse_financials(self, html: str, slug: str) -> dict[str, Any]:
        """Parse key financial ratios from Moneycontrol financials page."""
        soup = BeautifulSoup(html, "lxml")
        data: dict[str, Any] = {"slug": slug, "source": "moneycontrol"}

        # Parse ratio table rows
        table = soup.find("table", class_="mctable1")
        if not table:
            return data

        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            label = cells[0].get_text(strip=True).lower()
            value_text = cells[-1].get_text(strip=True)

            if "earning per share" in label or "eps" in label:
                data["eps"] = value_text
            elif "return on equity" in label or "roe" in label:
                data["roe"] = value_text
            elif "return on capital" in label or "roce" in label:
                data["roce"] = value_text
            elif "debt equity" in label or "debt/equity" in label:
                data["debt_equity"] = value_text
            elif "price to earning" in label or "p/e" in label:
                data["pe"] = value_text

        return data

    # ------------------------------------------------------------------
    # BaseScraper interface
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Fetch news from all categories."""
        return await self.fetch_news()

    async def save(self, data: list[dict[str, Any]]) -> int:
        """Persist news articles to the news table."""
        from mr_market_shared.db.models import News
        from mr_market_shared.db.session import get_session_manager

        manager = get_session_manager()
        saved = 0
        async with manager.session() as session:
            for article in data:
                news = News(
                    headline=article.get("headline"),
                    url=article.get("url"),
                    source="moneycontrol",
                    published_at=datetime.now(),
                )
                session.add(news)
                saved += 1
            await session.commit()
        logger.info("moneycontrol: saved %d news articles", saved)
        return saved
