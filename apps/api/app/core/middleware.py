"""Custom ASGI middleware for logging and rate limiting."""

from __future__ import annotations

import logging
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("mr_market.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status code, and duration.

    Example log line::

        INFO  POST /api/v1/chat 200 134.5ms
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        start = time.perf_counter()

        response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s %d %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )

        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Placeholder rate-limiting middleware.

    Will be backed by Redis sliding-window counters in a later phase.
    Currently passes all requests through.
    """

    def __init__(
        self,
        app: Any,
        requests_per_minute: int = 60,
    ) -> None:
        super().__init__(app)
        self._rpm = requests_per_minute

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # Phase 2: implement sliding window with Redis
        # client_ip = request.client.host if request.client else "unknown"
        # key = f"ratelimit:{client_ip}"
        # count = await redis.incr(key)
        # ...
        return await call_next(request)
