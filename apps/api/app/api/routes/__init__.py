"""Collect all API routers into a single top-level router."""

from fastapi import APIRouter

from app.api.routes.analyze import router as analyze_router
from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.portfolio import router as portfolio_router

api_router = APIRouter()

api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(chat_router, prefix="/chat", tags=["chat"])
api_router.include_router(analyze_router, prefix="/analyze", tags=["analyze"])
api_router.include_router(portfolio_router, prefix="/portfolio", tags=["portfolio"])
