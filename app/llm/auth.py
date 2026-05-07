"""OpenAI/Codex credential loader and PKCE login helpers.

The normal local path is the Gateway-style Codex OAuth flow:

  1. UI asks this module for an OpenAI PKCE auth URL.
  2. User signs in with ChatGPT/OpenAI in a new tab.
  3. User pastes the full redirect URL back into the app.
  4. We exchange the code and store Codex OAuth tokens in Redis.

The app prefers Codex OAuth tokens over every other source. Env API keys are
disabled by default so local demo traffic does not silently use the developer's
``OPENAI_API_KEY``.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from redis import asyncio as aioredis

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_AUTH_URL = "https://auth.openai.com/oauth/authorize"
CODEX_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_SCOPE = "openid profile email offline_access"

REDIS_API_KEY = "openai:api_key"
REDIS_CODEX_TOKENS = "openai:codex_oauth"
REDIS_PKCE_PREFIX = "openai:codex_pkce:"
PKCE_TTL_SECONDS = 15 * 60
REFRESH_WINDOW_SECONDS = 5 * 60

Source = Literal["codex_oauth", "codex_cli", "redis", "env", "none"]
CODEX_SOURCES = {"codex_oauth", "codex_cli"}


@dataclass(slots=True, frozen=True)
class AuthState:
    api_key: str | None
    source: Source
    codex_auth_path: str | None = None
    expires_at: int | None = None
    notes: tuple[str, ...] = ()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def using_fallback(self) -> bool:
        return self.source not in CODEX_SOURCES


@dataclass(slots=True, frozen=True)
class EffectiveModels:
    work: str
    router: str
    using_fallback: bool
    fallback_reason: str | None = None


def effective_models(
    auth: AuthState,
    settings: Settings | None = None,
) -> EffectiveModels:
    """Choose the model family from the resolved credential source."""
    settings = settings or get_settings()
    if auth.source in CODEX_SOURCES:
        return EffectiveModels(
            work=settings.openai_model_work,
            router=settings.openai_model_router,
            using_fallback=False,
        )
    reason = (
        "Codex is not connected, so Midas is using the backend OPENAI_API_KEY on GPT-4o mini."
        if auth.configured
        else "Codex is not connected and backend OPENAI_API_KEY is not set."
    )
    return EffectiveModels(
        work=settings.openai_fallback_model_work,
        router=settings.openai_fallback_model_router,
        using_fallback=True,
        fallback_reason=reason,
    )


def _candidate_codex_paths() -> list[Path]:
    home = Path.home()
    return [home / ".codex" / "auth.json"]


def _read_codex_auth() -> tuple[str | None, str | None, int | None]:
    """Return (access_token, path_used, expires_at). Tolerates known CLI schemas."""
    for p in _candidate_codex_paths():
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text())
        except Exception as e:  # noqa: BLE001
            logger.warning("could not read %s: %s", p, e)
            continue
        if not isinstance(data, dict):
            continue
        tokens = data.get("tokens")
        if isinstance(tokens, dict):
            v = tokens.get("access_token")
            if isinstance(v, str) and v:
                return v, str(p), _coerce_expires_at(tokens)
        # Older CLI builds may write a synthesized key. Treat it as legacy
        # fallback, not the preferred Codex OAuth source.
        if isinstance(data.get("OPENAI_API_KEY"), str) and data["OPENAI_API_KEY"]:
            return data["OPENAI_API_KEY"], str(p), None
    return None, None, None


def _coerce_expires_at(data: dict[str, Any]) -> int | None:
    for key in ("expires_at", "expiresAt", "expires_at_ms", "expiresAtMs"):
        raw = data.get(key)
        if isinstance(raw, (int, float)) and raw > 0:
            value = int(raw)
            return value // 1000 if value > 10_000_000_000 else value
    return None


async def _read_redis(redis: aioredis.Redis | None) -> str | None:
    if redis is None:
        return None
    try:
        v = await redis.get(REDIS_API_KEY)
        if isinstance(v, str) and v.strip():
            return v.strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("redis read for openai key failed: %s", e)
    return None


async def _read_codex_redis(redis: aioredis.Redis | None) -> dict[str, Any] | None:
    if redis is None:
        return None
    try:
        raw = await redis.get(REDIS_CODEX_TOKENS)
    except Exception as e:  # noqa: BLE001
        logger.warning("redis read for codex token failed: %s", e)
        return None
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


async def _store_codex_redis(redis: aioredis.Redis, data: dict[str, Any]) -> None:
    await redis.set(REDIS_CODEX_TOKENS, json.dumps(data))


async def load_state(redis: aioredis.Redis | None = None) -> AuthState:
    """Resolve the currently-active credential. Never raises."""
    notes: list[str] = []

    # 1. In-app Codex OAuth token.
    codex_data = await _read_codex_redis(redis)
    if codex_data:
        refreshed = await _refresh_codex_if_needed(redis, codex_data)
        if refreshed:
            codex_data = refreshed
        expires_at = _coerce_expires_at(codex_data)
        if expires_at is not None and expires_at <= int(time.time()):
            notes.append("stored Codex token is expired")
            codex_data = {}
        token = codex_data.get("access_token")
        if isinstance(token, str) and token:
            return AuthState(
                api_key=token,
                source="codex_oauth",
                expires_at=expires_at,
                notes=tuple(notes),
            )

    # 2. Codex CLI auth.json.
    codex_val, codex_path, codex_expires_at = await asyncio.to_thread(_read_codex_auth)
    if codex_val:
        notes.append(f"loaded from {codex_path}")
        return AuthState(
            api_key=codex_val,
            source="codex_cli",
            codex_auth_path=codex_path,
            expires_at=codex_expires_at,
            notes=tuple(notes),
        )

    # 3. Redis manual paste, retained as an explicit local fallback.
    redis_val = await _read_redis(redis)
    if redis_val:
        return AuthState(api_key=redis_val, source="redis", notes=tuple(notes))

    # 4. .env / process env fallback. This is the existing backend
    # OPENAI_API_KEY path, used only when Codex OAuth/CLI is unavailable.
    settings = get_settings()
    env_val = (settings.openai_api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
    if settings.openai_allow_env_credentials and env_val:
        return AuthState(api_key=env_val, source="env", notes=tuple(notes))

    return AuthState(api_key=None, source="none", notes=tuple(notes))


async def store_redis_key(
    redis: aioredis.Redis, key: str, ttl_seconds: int = 86400
) -> None:
    """Persist a manually-pasted key with a 24h TTL by default."""
    if not key or not key.strip():
        raise ValueError("empty key")
    await redis.set(REDIS_API_KEY, key.strip(), ex=ttl_seconds)


async def clear_redis_key(redis: aioredis.Redis) -> None:
    try:
        await redis.delete(REDIS_API_KEY)
    except Exception:  # noqa: BLE001
        pass


async def initiate_codex_login(redis: aioredis.Redis) -> dict[str, str]:
    """Create a short-lived PKCE session and return the OpenAI auth URL."""
    settings = get_settings()
    verifier = _base64url(secrets.token_bytes(32))
    challenge = _base64url(hashlib.sha256(verifier.encode("ascii")).digest())
    state = _base64url(secrets.token_bytes(16))

    await redis.set(
        f"{REDIS_PKCE_PREFIX}{state}",
        json.dumps(
            {
                "verifier": verifier,
                "redirect_uri": settings.openai_redirect_uri,
                "created_at": int(time.time()),
            }
        ),
        ex=PKCE_TTL_SECONDS,
    )

    params = {
        "client_id": CODEX_CLIENT_ID,
        "redirect_uri": settings.openai_redirect_uri,
        "response_type": "code",
        "scope": CODEX_SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
    }
    return {
        "auth_url": f"{CODEX_AUTH_URL}?{urlencode(params)}",
        "state": state,
        "redirect_uri": settings.openai_redirect_uri,
    }


async def complete_codex_login(redis: aioredis.Redis, callback_url: str) -> None:
    parsed = urlparse(callback_url.strip())
    qs = parse_qs(parsed.query)
    error = _single(qs, "error")
    if error:
        description = _single(qs, "error_description") or error
        raise ValueError(description)
    code = _single(qs, "code")
    state = _single(qs, "state")
    if not code or not state:
        raise ValueError("callback URL must include code and state")

    session_key = f"{REDIS_PKCE_PREFIX}{state}"
    raw = await redis.get(session_key)
    if not isinstance(raw, str):
        raise ValueError("login session expired; start again")
    await redis.delete(session_key)

    session = json.loads(raw)
    verifier = str(session.get("verifier") or "")
    redirect_uri = str(
        session.get("redirect_uri") or get_settings().openai_redirect_uri
    )
    if not verifier:
        raise ValueError("login session is invalid; start again")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            CODEX_TOKEN_URL,
            json={
                "client_id": CODEX_CLIENT_ID,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if resp.status_code >= 400:
        raise ValueError(_safe_error(resp))
    data = resp.json()
    await _store_token_response(redis, data)


async def clear_codex_login(redis: aioredis.Redis) -> None:
    await redis.delete(REDIS_CODEX_TOKENS)


async def _refresh_codex_if_needed(
    redis: aioredis.Redis | None,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    if redis is None:
        return None
    refresh_token = data.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        return None
    expires_at = _coerce_expires_at(data)
    if (
        expires_at is not None
        and expires_at - int(time.time()) > REFRESH_WINDOW_SECONDS
    ):
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                CODEX_TOKEN_URL,
                json={
                    "client_id": CODEX_CLIENT_ID,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        if resp.status_code >= 400:
            logger.warning("codex refresh failed: %s", _safe_error(resp))
            return None
        next_data = _token_payload(resp.json(), fallback_refresh_token=refresh_token)
        await _store_codex_redis(redis, next_data)
        return next_data
    except Exception as e:  # noqa: BLE001
        logger.warning("codex refresh failed: %s", e)
        return None


async def _store_token_response(
    redis: aioredis.Redis, response: dict[str, Any]
) -> None:
    await _store_codex_redis(redis, _token_payload(response))


def _token_payload(
    response: dict[str, Any], *, fallback_refresh_token: str | None = None
) -> dict[str, Any]:
    access_token = response.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ValueError("OpenAI did not return an access token")
    refresh_token = response.get("refresh_token") or fallback_refresh_token
    expires_in = response.get("expires_in")
    ttl = (
        int(expires_in)
        if isinstance(expires_in, (int, float)) and expires_in > 0
        else 864_000
    )
    payload = {
        "access_token": access_token,
        "expires_at": int(time.time()) + ttl,
        "connected_at": int(time.time()),
    }
    if isinstance(refresh_token, str) and refresh_token:
        payload["refresh_token"] = refresh_token
    return payload


def _single(qs: dict[str, list[str]], key: str) -> str | None:
    values = qs.get(key) or []
    return values[0] if values else None


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _safe_error(resp: httpx.Response) -> str:
    text = resp.text[:500]
    return f"OpenAI OAuth error {resp.status_code}: {text}"
