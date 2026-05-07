"""Retry decorator with exponential backoff and configurable policy."""

import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class RetryPolicy:
    """Configurable retry policy with exponential backoff.

    Attributes:
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds before the first retry.
        max_delay: Upper bound on the delay between retries.
        backoff_factor: Multiplier applied to the delay after each retry.
        retryable_exceptions: Tuple of exception types that trigger a retry.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.retryable_exceptions = retryable_exceptions

    def compute_delay(self, attempt: int) -> float:
        """Compute the delay for a given attempt number (0-indexed)."""
        delay = self.base_delay * (self.backoff_factor ** attempt)
        return min(delay, self.max_delay)


def with_retry(
    policy: RetryPolicy | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator that retries an async function according to a RetryPolicy.

    Usage:
        @with_retry(RetryPolicy(max_retries=5, base_delay=0.5))
        async def fetch_data(url: str) -> dict: ...
    """
    if policy is None:
        policy = RetryPolicy()

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception: Exception | None = None
            for attempt in range(policy.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except policy.retryable_exceptions as exc:
                    last_exception = exc
                    if attempt < policy.max_retries:
                        delay = policy.compute_delay(attempt)
                        logger.warning(
                            "Retry %d/%d for %s after %.1fs — %s: %s",
                            attempt + 1,
                            policy.max_retries,
                            func.__qualname__,
                            delay,
                            type(exc).__name__,
                            exc,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "All %d retries exhausted for %s — %s: %s",
                            policy.max_retries,
                            func.__qualname__,
                            type(exc).__name__,
                            exc,
                        )
            raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator
