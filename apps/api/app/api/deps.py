"""Shared FastAPI dependencies injected into route handlers."""

from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis import RedisCache
from app.config import Settings, get_settings
from app.core.security import JWTAuth
from mr_market_shared.db.session import get_db as _shared_get_db


# ---------------------------------------------------------------------------
# Database session
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session (delegates to the shared package)."""
    async for session in _shared_get_db():
        yield session


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

SettingsDep = Annotated[Settings, Depends(get_settings)]


# ---------------------------------------------------------------------------
# Redis cache
# ---------------------------------------------------------------------------

def get_redis(request: Request) -> RedisCache:
    """Return the Redis cache instance attached during startup."""
    cache: RedisCache | None = getattr(request.app.state, "redis", None)
    if cache is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis is not available",
        )
    return cache


RedisDep = Annotated[RedisCache, Depends(get_redis)]


# ---------------------------------------------------------------------------
# Current authenticated user
# ---------------------------------------------------------------------------

async def get_current_user(
    request: Request,
    settings: SettingsDep,
) -> UUID:
    """Extract and verify the JWT from the Authorization header.

    Returns the ``user_id`` (UUID) embedded in the token payload.
    Raises 401 if the token is missing or invalid.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.removeprefix("Bearer ").strip()
    jwt_auth = JWTAuth(
        secret=settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    payload = jwt_auth.verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
        )

    return UUID(user_id_str)


CurrentUserDep = Annotated[UUID, Depends(get_current_user)]
DBSessionDep = Annotated[AsyncSession, Depends(get_db)]
