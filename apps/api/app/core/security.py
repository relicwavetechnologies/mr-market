"""JWT authentication utilities."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import jwt

logger = logging.getLogger(__name__)


class JWTAuth:
    """Create and verify JWT tokens for user authentication.

    Uses PyJWT (``import jwt``) with HS256 by default.
    """

    def __init__(
        self,
        secret: str,
        algorithm: str = "HS256",
        expiry_minutes: int = 1440,  # 24 hours
    ) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._expiry_minutes = expiry_minutes

    def create_token(
        self,
        user_id: UUID,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        """Generate a signed JWT for the given user.

        The ``sub`` claim contains the stringified user UUID.
        """
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=self._expiry_minutes),
        }
        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def verify_token(self, token: str) -> dict[str, Any] | None:
        """Decode and verify a JWT.

        Returns the payload dict on success, or ``None`` if the token is
        invalid or expired.
        """
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.debug("Token expired")
            return None
        except jwt.InvalidTokenError as exc:
            logger.debug("Invalid token: %s", exc)
            return None

    def refresh_token(self, token: str) -> str | None:
        """Issue a fresh token if the existing one is still valid.

        Returns ``None`` if the original token cannot be verified.
        """
        payload = self.verify_token(token)
        if payload is None:
            return None

        user_id = UUID(payload["sub"])
        extra = {k: v for k, v in payload.items() if k not in ("sub", "iat", "exp")}
        return self.create_token(user_id, extra_claims=extra or None)
