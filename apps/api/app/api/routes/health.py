"""System health-check endpoint."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.deps import DBSessionDep, RedisDep
from mr_market_shared.db.session import get_session_manager

logger = logging.getLogger(__name__)

router = APIRouter()


class ComponentHealth(BaseModel):
    """Health status for a single infrastructure component."""
    name: str
    status: str  # "ok" | "degraded" | "down"
    latency_ms: float | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    """Aggregated health status of the system."""
    status: str  # "healthy" | "degraded" | "unhealthy"
    timestamp: str
    components: list[ComponentHealth] = Field(default_factory=list)


@router.get("", response_model=HealthResponse)
async def health_check(
    db: DBSessionDep,
    redis: RedisDep,
) -> HealthResponse:
    """Run health checks against DB, Redis, and report overall status."""
    components: list[ComponentHealth] = []
    overall = "healthy"

    # -- Database ---------------------------------------------------------------
    db_health = await _check_database(db)
    components.append(db_health)
    if db_health.status != "ok":
        overall = "degraded"

    # -- Redis ------------------------------------------------------------------
    redis_health = await _check_redis(redis)
    components.append(redis_health)
    if redis_health.status != "ok":
        overall = "degraded"

    if all(c.status == "down" for c in components):
        overall = "unhealthy"

    return HealthResponse(
        status=overall,
        timestamp=datetime.now(timezone.utc).isoformat(),
        components=components,
    )


async def _check_database(db: Any) -> ComponentHealth:
    """Ping the database with a lightweight query."""
    import time
    from sqlalchemy import text

    start = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        elapsed = (time.perf_counter() - start) * 1000
        return ComponentHealth(name="database", status="ok", latency_ms=round(elapsed, 2))
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        logger.warning("Database health check failed: %s", exc)
        return ComponentHealth(
            name="database", status="down", latency_ms=round(elapsed, 2), detail=str(exc)
        )


async def _check_redis(redis: Any) -> ComponentHealth:
    """Ping the Redis server."""
    import time

    start = time.perf_counter()
    try:
        pong = await redis.ping()
        elapsed = (time.perf_counter() - start) * 1000
        status = "ok" if pong else "degraded"
        return ComponentHealth(name="redis", status=status, latency_ms=round(elapsed, 2))
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        logger.warning("Redis health check failed: %s", exc)
        return ComponentHealth(
            name="redis", status="down", latency_ms=round(elapsed, 2), detail=str(exc)
        )
