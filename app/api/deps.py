from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.db.session import get_session
from app.security.tokens import TokenDecodeError, decode, require_type


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
) -> User:
    if not authorization:
        raise _unauthorized("missing bearer token")
    return await _user_from_authorization(authorization, session=session)


async def get_current_user_optional(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
) -> User | None:
    if not authorization:
        return None
    return await _user_from_authorization(authorization, session=session)


async def _user_from_authorization(authorization: str, *, session: AsyncSession) -> User:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("invalid authorization header")

    try:
        payload = decode(token)
        require_type(payload, "access")
        user_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, TokenDecodeError, ValueError) as e:
        raise _unauthorized("invalid token") from e

    user = await session.get(User, user_id)
    if user is None:
        raise _unauthorized("user not found")
    return user


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )
