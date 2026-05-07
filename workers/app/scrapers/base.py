"""Base scraper with rate limiting, user-agent rotation, and retry logic."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Realistic browser user-agent strings rotated per request to avoid blocks.
_USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


class RateLimiter:
    """Token-bucket rate limiter for async HTTP requests."""

    def __init__(self, requests_per_second: float) -> None:
        self._interval = 1.0 / requests_per_second
        self._last_request: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until the next request is permitted."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self._interval:
                await asyncio.sleep(self._interval - elapsed)
            self._last_request = time.monotonic()


class UserAgentRotator:
    """Round-robin user-agent selector with jitter."""

    def __init__(self, agents: list[str] | None = None) -> None:
        self._agents = agents or _USER_AGENTS

    def get(self) -> str:
        return random.choice(self._agents)  # noqa: S311


class BaseScraper(ABC):
    """Abstract base for all Mr. Market scrapers.

    Subclasses must implement :meth:`scrape` and set ``name``,
    ``source_url``, and ``rate_limit`` (requests per second).
    """

    name: str
    source_url: str
    rate_limit: float  # requests per second

    # Retry policy
    max_retries: int = 3
    retry_backoff: float = 2.0  # exponential backoff base (seconds)

    def __init__(self) -> None:
        self._rate_limiter = RateLimiter(self.rate_limit)
        self._ua_rotator = UserAgentRotator()
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazily create a shared httpx async client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
                http2=False,
            )
        return self._client

    async def fetch(self, url: str, *, as_json: bool = False) -> str | dict[str, Any]:
        """Fetch *url* with rate limiting, UA rotation, and retries.

        Parameters
        ----------
        url:
            Target URL.
        as_json:
            If ``True``, parse the response as JSON and return a dict.

        Returns
        -------
        str | dict
            Response body as text or parsed JSON.
        """
        client = await self._get_client()
        last_exc: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            await self._rate_limiter.acquire()
            headers = {"User-Agent": self._ua_rotator.get()}
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                if as_json:
                    return response.json()  # type: ignore[return-value]
                return response.text
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_exc = exc
                wait = self.retry_backoff ** attempt + random.uniform(0, 1)  # noqa: S311
                logger.warning(
                    "%s: attempt %d/%d for %s failed (%s), retrying in %.1fs",
                    self.name,
                    attempt,
                    self.max_retries,
                    url,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)

        raise RuntimeError(
            f"{self.name}: all {self.max_retries} attempts failed for {url}"
        ) from last_exc

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def scrape(self) -> list[dict[str, Any]]:
        """Run the scraping pipeline and return structured records."""
        ...

    async def save(self, data: list[dict[str, Any]]) -> int:
        """Persist *data* to the database via shared ORM models.

        Subclasses may override for custom upsert logic. The default
        implementation delegates to a bulk insert through the shared
        session manager.

        Returns the number of records saved.
        """
        from mr_market_shared.db.session import get_session_manager

        manager = get_session_manager()
        async with manager.session() as session:
            model_cls = self._get_model_class()
            objects = [model_cls(**row) for row in data]
            session.add_all(objects)
            await session.commit()
            logger.info("%s: saved %d records", self.name, len(objects))
            return len(objects)

    def _get_model_class(self) -> type:
        """Return the SQLAlchemy model class for this scraper's data.

        Subclasses should override this to return the appropriate model.
        """
        raise NotImplementedError(
            f"{self.name} must override _get_model_class() for save()"
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> list[dict[str, Any]]:
        """Convenience: scrape, save, and return results."""
        logger.info("%s: starting scrape from %s", self.name, self.source_url)
        data = await self.scrape()
        if data:
            await self.save(data)
        logger.info("%s: completed — %d records", self.name, len(data))
        return data

    async def close(self) -> None:
        """Shut down the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
