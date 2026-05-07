"""Async Redis cache wrapper with JSON serialisation and TTL support."""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Default TTL for cached values (seconds)
_DEFAULT_TTL = 300  # 5 minutes


class RedisCache:
    """Thin async wrapper around a ``redis.asyncio`` connection.

    All values are JSON-serialised before storage and deserialised on
    retrieval, so callers work with plain Python dicts/lists.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def get(self, key: str) -> Any | None:
        """Retrieve and deserialise a cached value.

        Returns ``None`` on cache miss or deserialisation failure.
        """
        raw = await self._redis.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to deserialise cache value for key=%s", key)
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = _DEFAULT_TTL,
    ) -> None:
        """Serialise and store a value with an expiration TTL (seconds)."""
        serialised = json.dumps(value, default=str)
        await self._redis.setex(key, ttl, serialised)

    async def delete(self, key: str) -> bool:
        """Remove a key from the cache. Returns True if the key existed."""
        result = await self._redis.delete(key)
        return bool(result)

    async def exists(self, key: str) -> bool:
        """Check whether a key exists in the cache."""
        return bool(await self._redis.exists(key))

    async def ping(self) -> bool:
        """Health check — returns True if Redis responds to PING."""
        try:
            return await self._redis.ping()
        except Exception:
            return False

    async def set_many(
        self,
        mapping: dict[str, Any],
        ttl: int = _DEFAULT_TTL,
    ) -> None:
        """Store multiple key-value pairs in a single pipeline."""
        async with self._redis.pipeline(transaction=False) as pipe:
            for key, value in mapping.items():
                serialised = json.dumps(value, default=str)
                pipe.setex(key, ttl, serialised)
            await pipe.execute()

    async def get_many(self, keys: list[str]) -> dict[str, Any | None]:
        """Retrieve multiple keys in a single round-trip."""
        values = await self._redis.mget(keys)
        result: dict[str, Any | None] = {}
        for key, raw in zip(keys, values, strict=True):
            if raw is None:
                result[key] = None
            else:
                try:
                    result[key] = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    result[key] = None
        return result

    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment a counter key and return the new value."""
        return await self._redis.incrby(key, amount)

    async def ttl(self, key: str) -> int:
        """Return remaining TTL in seconds (-1 if no expiry, -2 if missing)."""
        return await self._redis.ttl(key)
