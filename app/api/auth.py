"""OpenAI Codex credential management endpoints.

GET    /auth/openai/status      Where is the active key coming from?
POST   /auth/openai/codex/initiate
                                    Start the Codex OAuth PKCE flow.
POST   /auth/openai/codex/complete
                                    Paste a redirect URL and store tokens.
DELETE /auth/openai/codex       Forget stored Codex OAuth tokens.
POST   /auth/openai/key         Paste / update a key (24h Redis TTL).
DELETE /auth/openai/key         Forget the pasted key (env / codex still active).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import get_settings
from app.llm.auth import (
    clear_codex_login,
    clear_redis_key,
    complete_codex_login,
    effective_models,
    initiate_codex_login,
    load_state,
    store_redis_key,
)

router = APIRouter(prefix="/api/auth/openai", tags=["auth"])


class StatusResponse(BaseModel):
    configured: bool
    source: str
    model_work: str
    model_router: str
    using_fallback: bool = False
    fallback_reason: str | None = None
    codex_auth_path: str | None = None
    expires_at: int | None = None
    hint: str | None = None


class PasteKeyPayload(BaseModel):
    api_key: str = Field(..., min_length=8, max_length=512)
    ttl_seconds: int = Field(default=86400, ge=60, le=60 * 60 * 24 * 30)


class CodexInitiateResponse(BaseModel):
    auth_url: str
    state: str
    redirect_uri: str


class CodexCompletePayload(BaseModel):
    callback_url: str = Field(..., min_length=10, max_length=4096)


@router.get("/status", response_model=StatusResponse)
async def status(request: Request) -> StatusResponse:
    redis = getattr(request.app.state, "redis", None)
    state = await load_state(redis)
    settings = get_settings()
    models = effective_models(state, settings)
    hint: str | None = None
    if not state.configured:
        hint = (
            "Codex is not connected and backend OPENAI_API_KEY is not set. "
            "Connect OpenAI to use GPT-5.4 mini, or set OPENAI_API_KEY to use GPT-4o mini fallback."
        )
    elif models.using_fallback:
        hint = (
            "Codex is not connected, so Midas is using backend OPENAI_API_KEY on GPT-4o mini. "
            "Connect OpenAI to switch back to GPT-5.4 mini."
        )
    return StatusResponse(
        configured=state.configured,
        source=state.source,
        model_work=models.work,
        model_router=models.router,
        using_fallback=models.using_fallback,
        fallback_reason=models.fallback_reason,
        codex_auth_path=state.codex_auth_path,
        expires_at=state.expires_at,
        hint=hint,
    )


@router.post("/codex/initiate", response_model=CodexInitiateResponse)
async def initiate_codex(request: Request) -> CodexInitiateResponse:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="redis unavailable")
    return CodexInitiateResponse(**(await initiate_codex_login(redis)))


@router.post("/codex/complete", response_model=StatusResponse)
async def complete_codex(
    payload: CodexCompletePayload, request: Request
) -> StatusResponse:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="redis unavailable")
    try:
        await complete_codex_login(redis, payload.callback_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return await status(request)


@router.delete("/codex", response_model=StatusResponse)
async def disconnect_codex(request: Request) -> StatusResponse:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="redis unavailable")
    await clear_codex_login(redis)
    return await status(request)


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
