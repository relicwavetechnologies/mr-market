"""RSS feed adapters — Pulse, Moneycontrol, Economic Times.

Each function returns a list of `RawHeadline` dicts. No DB writes, no
ticker-tagging here — that's the news_service's job.

Failure semantics: on any error we return [] and let the caller treat the
source as temporarily unavailable. We never raise.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import feedparser
import httpx

logger = logging.getLogger(__name__)

SourceName = Literal["pulse", "moneycontrol", "et_markets"]


@dataclass(slots=True)
class RawHeadline:
    source: SourceName
    title: str
    url: str
    published_at: datetime
    summary: str | None


_FEEDS: dict[SourceName, str] = {
    "pulse": "https://pulse.zerodha.com/feed.php",
    "moneycontrol": "https://www.moneycontrol.com/rss/marketreports.xml",
    "et_markets": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
}

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _parse_pubdate(raw: object) -> datetime:
    """Best-effort parse of an RSS pubDate. Falls back to 'now' on failure."""
    if isinstance(raw, str) and raw:
        try:
            # feedparser parses dates into struct_time; raw string is a fallback.
            from email.utils import parsedate_to_datetime

            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)


def _parse_feed(source: SourceName, body: bytes) -> list[RawHeadline]:
    parsed = feedparser.parse(body)
    out: list[RawHeadline] = []
    for entry in parsed.entries or []:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        # feedparser exposes published_parsed (struct_time) for most well-formed
        # feeds. Fall back to the raw `published` string if absent.
        if entry.get("published_parsed"):
            try:
                published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                published_at = _parse_pubdate(entry.get("published"))
        else:
            published_at = _parse_pubdate(entry.get("published"))

        summary = entry.get("summary") or entry.get("description")
        if isinstance(summary, str):
            summary = summary.strip()[:1000] or None
        else:
            summary = None

        out.append(
            RawHeadline(
                source=source,
                title=title[:500],
                url=link[:1000],
                published_at=published_at,
                summary=summary,
            )
        )
    return out


async def _fetch_one(
    client: httpx.AsyncClient, source: SourceName, url: str
) -> list[RawHeadline]:
    try:
        r = await client.get(url, headers={"User-Agent": _USER_AGENT})
        if r.status_code != 200:
            logger.warning("rss source=%s HTTP %s", source, r.status_code)
            return []
        return _parse_feed(source, r.content)
    except Exception as e:  # noqa: BLE001
        logger.warning("rss source=%s error: %s", source, e)
        return []


async def fetch_all(*, timeout_s: float = 10.0) -> list[RawHeadline]:
    """Fan-out to every configured feed in parallel; return their union."""
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        groups = await asyncio.gather(
            *[_fetch_one(client, name, url) for name, url in _FEEDS.items()]
        )
    flat: list[RawHeadline] = []
    for g in groups:
        flat.extend(g)
    return flat
