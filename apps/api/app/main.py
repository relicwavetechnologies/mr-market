"""FastAPI application factory and lifespan management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.cache.redis import RedisCache
from app.config import get_settings
from app.core.middleware import RequestLoggingMiddleware
from mr_market_shared.db.session import init_session_manager, get_session_manager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle for the FastAPI application.

    On startup:
      - Initialise the async database engine and session factory.
      - Establish a Redis connection pool.

    On shutdown:
      - Close the Redis pool.
      - Dispose of the SQLAlchemy engine.
    """
    settings = get_settings()

    # -- Database ---------------------------------------------------------------
    session_manager = init_session_manager(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
    )

    # -- Redis ------------------------------------------------------------------
    redis_pool = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )
    app.state.redis = RedisCache(redis_pool)

    yield

    # -- Shutdown ---------------------------------------------------------------
    await redis_pool.aclose()
    await get_session_manager().close()


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Mr. Market API",
        description="AI-powered Indian stock market trading assistant",
        version="0.1.0",
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    # -- Middleware --------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    # -- Routers ----------------------------------------------------------------
    app.include_router(api_router, prefix="/api/v1")

    # -- Root health probe ------------------------------------------------------
    @app.get("/", tags=["root"])
    async def root() -> dict[str, str]:
        return {"status": "ok", "service": "mr-market-api"}

    return app
