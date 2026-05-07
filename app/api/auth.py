"""OpenAI credential management endpoints.

  GET    /auth/openai/status      Where is the active key coming from?
  POST   /auth/openai/key         Paste / update a key (24h Redis TTL).
  DELETE /auth/openai/key         Forget the pasted key (env / codex still active).

For the canonical "Sign in with ChatGPT" flow, we delegate to the official
OpenAI Codex CLI: install + run `codex login` once, this server reads
``~/.codex/auth.json`` automatically. That file is refreshed by the codex
CLI's own token-refresh logic; we just re-read on every request.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import get_settings
from app.llm.auth import clear_redis_key, load_state, store_redis_key

router = APIRouter(prefix="/api/auth/openai", tags=["auth"])


class StatusResponse(BaseModel):
    configured: bool
    source: str
    model_work: str
    model_router: str
    codex_auth_path: str | None = None
    hint: str | None = None


class PasteKeyPayload(BaseModel):
    api_key: str = Field(..., min_length=8, max_length=512)
    ttl_seconds: int = Field(default=86400, ge=60, le=60 * 60 * 24 * 30)


@router.get("/status", response_model=StatusResponse)
async def status(request: Request) -> StatusResponse:
    redis = getattr(request.app.state, "redis", None)
    state = await load_state(redis)
    settings = get_settings()
    hint: str | None = None
    if not state.configured:
        hint = (
            "No OpenAI credential found. Either (a) set OPENAI_API_KEY in .env, "
            "(b) install the codex CLI and run `codex login`, or "
            "(c) POST /auth/openai/key with your key."
        )
    return StatusResponse(
        configured=state.configured,
        source=state.source,
        model_work=settings.openai_model_work,
        model_router=settings.openai_model_router,
        codex_auth_path=state.codex_auth_path,
        hint=hint,
    )


@router.post("/key", response_model=StatusResponse)
async def paste_key(payload: PasteKeyPayload, request: Request) -> StatusResponse:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="redis unavailable")
    await store_redis_key(redis, payload.api_key, ttl_seconds=payload.ttl_seconds)
    return await status(request)


@router.delete("/key", response_model=StatusResponse)
async def clear_key(request: Request) -> StatusResponse:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="redis unavailable")
    await clear_redis_key(redis)
    return await status(request)
