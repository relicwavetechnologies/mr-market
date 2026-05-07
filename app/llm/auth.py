"""OpenAI credential loader with three sources, in priority order:

  1. Redis  (key: ``openai:api_key``)         — latest "paste a key" wins.
  2. Env    (``OPENAI_API_KEY``)              — classic .env path.
  3. Codex  (``~/.codex/auth.json``)          — written by `codex login`.

We re-read on every call so that:
  * `codex login` refreshes are picked up without restarting the server.
  * A user pasting a key in the UI takes effect immediately.

The file-based path supports the two on-disk formats produced by the
official OpenAI Codex CLI:

    {"OPENAI_API_KEY": "sk-..."}
    {"OPENAI_API_KEY": "...",
     "tokens": {"access_token": "...", "refresh_token": "...", ...}}
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from redis import asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)

REDIS_KEY = "openai:api_key"

Source = Literal["redis", "env", "codex_cli", "none"]


@dataclass(slots=True, frozen=True)
class AuthState:
    api_key: str | None
    source: Source
    codex_auth_path: str | None = None
    notes: tuple[str, ...] = ()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def _candidate_codex_paths() -> list[Path]:
    home = Path.home()
    return [home / ".codex" / "auth.json"]


def _read_codex_auth() -> tuple[str | None, str | None]:
    """Return (api_key, path_used). Tolerates multiple known schema versions."""
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
        # Most common layout — codex writes a synthesized OPENAI_API_KEY at the top level.
        if isinstance(data.get("OPENAI_API_KEY"), str) and data["OPENAI_API_KEY"]:
            return data["OPENAI_API_KEY"], str(p)
        # Newer codex versions: tokens.access_token (use as bearer; OpenAI SDK
        # ships it in the Authorization header just like an API key).
        tokens = data.get("tokens")
        if isinstance(tokens, dict):
            for k in ("access_token", "id_token"):
                v = tokens.get(k)
                if isinstance(v, str) and v:
                    return v, str(p)
    return None, None


async def _read_redis(redis: aioredis.Redis | None) -> str | None:
    if redis is None:
        return None
    try:
        v = await redis.get(REDIS_KEY)
        if isinstance(v, str) and v.strip():
            return v.strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("redis read for openai key failed: %s", e)
    return None


async def load_state(redis: aioredis.Redis | None = None) -> AuthState:
    """Resolve the currently-active credential. Never raises."""
    notes: list[str] = []

    # 1. Redis (manual paste wins)
    redis_val = await _read_redis(redis)
    if redis_val:
        return AuthState(api_key=redis_val, source="redis", notes=tuple(notes))

    # 2. .env / process env (pydantic-settings reads .env on import)
    settings = get_settings()
    env_val = (settings.openai_api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
    if env_val:
        return AuthState(api_key=env_val, source="env", notes=tuple(notes))

    # 3. Codex CLI auth.json
    codex_val, codex_path = await asyncio.to_thread(_read_codex_auth)
    if codex_val:
        notes.append(f"loaded from {codex_path}")
        return AuthState(
            api_key=codex_val,
            source="codex_cli",
            codex_auth_path=codex_path,
            notes=tuple(notes),
        )

    return AuthState(api_key=None, source="none", notes=tuple(notes))


async def store_redis_key(redis: aioredis.Redis, key: str, ttl_seconds: int = 86400) -> None:
    """Persist a manually-pasted key with a 24h TTL by default."""
    if not key or not key.strip():
        raise ValueError("empty key")
    await redis.set(REDIS_KEY, key.strip(), ex=ttl_seconds)


async def clear_redis_key(redis: aioredis.Redis) -> None:
    try:
        await redis.delete(REDIS_KEY)
    except Exception:  # noqa: BLE001
        pass
