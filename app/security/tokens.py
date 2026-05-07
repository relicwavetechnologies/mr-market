from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from jwt import InvalidTokenError

from app.config import get_settings

TokenType = Literal["access", "refresh"]


class TokenDecodeError(ValueError):
    pass


def issue_access(sub: str, ttl: timedelta | None = None, *, secret: str | None = None) -> str:
    settings = get_settings()
    ttl = ttl or timedelta(minutes=settings.jwt_access_ttl_min)
    return _issue(sub, token_type="access", ttl=ttl, secret=secret or settings.jwt_secret)


def issue_refresh(sub: str, ttl: timedelta | None = None, *, secret: str | None = None) -> str:
    settings = get_settings()
    ttl = ttl or timedelta(days=settings.jwt_refresh_ttl_days)
    return _issue(sub, token_type="refresh", ttl=ttl, secret=secret or settings.jwt_secret)


def decode(token: str, *, secret: str | None = None) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            secret or get_settings().jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub", "typ"]},
        )
    except InvalidTokenError as e:
        raise TokenDecodeError(str(e)) from e


def require_type(payload: dict[str, Any], token_type: TokenType) -> None:
    if payload.get("typ") != token_type:
        raise TokenDecodeError("wrong token type")


def _issue(sub: str, *, token_type: TokenType, ttl: timedelta, secret: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": sub,
            "typ": token_type,
            "iat": now,
            "exp": now + ttl,
        },
        secret,
        algorithm="HS256",
    )
