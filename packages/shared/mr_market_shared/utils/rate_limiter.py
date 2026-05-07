"""Async rate limiter using a token-bucket approach with asyncio semaphore."""

import asyncio
import time


class RateLimiter:
    """Configurable async rate limiter.

    Limits the number of concurrent requests and enforces a minimum
    interval between requests to respect API rate limits.

    Usage:
        limiter = RateLimiter(requests_per_second=5, max_concurrent=10)
        async with limiter:
            await make_request()
    """

    def __init__(
        self,
        requests_per_second: float = 5.0,
        max_concurrent: int = 10,
    ) -> None:
        self.min_interval = 1.0 / requests_per_second
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a rate-limited slot."""
        await self._semaphore.acquire()
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self._last_request_time = time.monotonic()

    def release(self) -> None:
        """Release a rate-limited slot."""
        self._semaphore.release()

    async def __aenter__(self) -> "RateLimiter":
        await self.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self.release()
