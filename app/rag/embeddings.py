"""OpenAI embedding wrapper.

Uses `text-embedding-3-small` (1536-dim) — the cheapest sensible choice
for English-language financial text. Cost ~$0.02 / 1M tokens; an entire
annual report (~80K tokens) embeds for ~₹0.13.

Batches the input in groups of 100 to fit OpenAI's batch limits, with a
defensive size cap on each chunk text (8K chars) before sending.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from openai import AsyncOpenAI

from app.llm.auth import load_state
from redis import asyncio as aioredis

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536
BATCH_SIZE = 100
MAX_INPUT_CHARS = 8000  # ~2K tokens; chunks are smaller in practice


async def _client(redis: aioredis.Redis | None = None) -> AsyncOpenAI:
    auth = await load_state(redis)
    if not auth.configured or auth.api_key is None:
        raise RuntimeError("OpenAI credential not configured (set OPENAI_API_KEY or codex login)")
    return AsyncOpenAI(api_key=auth.api_key)


def _truncate(s: str) -> str:
    return s if len(s) <= MAX_INPUT_CHARS else s[:MAX_INPUT_CHARS]


async def embed_batch(
    texts: Sequence[str],
    *,
    redis: aioredis.Redis | None = None,
    model: str = EMBEDDING_MODEL,
) -> list[list[float]]:
    """Embed a sequence of strings; preserves input order."""
    if not texts:
        return []
    client = await _client(redis)
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = [_truncate(t) for t in texts[i : i + BATCH_SIZE]]
        # Async retry: 1 retry on the whole batch — embeddings rarely flake.
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                resp = await client.embeddings.create(model=model, input=batch)
                out.extend([d.embedding for d in resp.data])
                last_err = None
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                logger.warning("embed batch %d (try %d) failed: %s", i, attempt, e)
                await asyncio.sleep(0.5)
        if last_err is not None:
            raise last_err
    return out


async def embed_one(
    text: str,
    *,
    redis: aioredis.Redis | None = None,
    model: str = EMBEDDING_MODEL,
) -> list[float]:
    """Convenience for the retrieval path (one-shot query embedding)."""
    out = await embed_batch([text], redis=redis, model=model)
    return out[0] if out else []
