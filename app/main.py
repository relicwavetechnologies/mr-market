from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis import asyncio as aioredis

from app.api import (
    auth,
    backtest,
    chat,
    chats,
    deals,
    health,
    holding,
    levels,
    news,
    portfolio,
    quote,
    research,
    screener,
    technicals,
    users,
    watchlist,
)
from app.config import get_settings

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log.info("startup", env=settings.env)

    # Redis pool for the app's lifetime.
    app.state.redis = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    try:
        await app.state.redis.ping()
        log.info("redis_connected", url=settings.redis_url)
    except Exception as e:  # noqa: BLE001
        log.warning("redis_ping_failed", error=str(e))

    yield

    try:
        await app.state.redis.aclose()
    except Exception:  # noqa: BLE001
        pass
    log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Midas",
        version="0.1.0",
        description="AI trading assistant — Phase 1 local demo",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:5174"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(chats.router)
    app.include_router(quote.router)
    app.include_router(news.router)
    app.include_router(technicals.router)
    app.include_router(levels.router)
    app.include_router(holding.router)
    app.include_router(deals.router)
    app.include_router(research.router)
    # Phase-3 stub endpoints (day-1 hand-off; real impl in P3-A2 → P3-A7).
    app.include_router(screener.router)
    app.include_router(portfolio.router)
    app.include_router(backtest.router)
    app.include_router(watchlist.router)
    app.include_router(chat.router)
    return app


app = create_app()
