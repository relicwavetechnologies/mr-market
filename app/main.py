from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.config import get_settings

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    log.info("startup", env=settings.env)
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Mr. Market",
        version="0.1.0",
        description="AI trading assistant — Phase 1 local demo",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    return app


app = create_app()
