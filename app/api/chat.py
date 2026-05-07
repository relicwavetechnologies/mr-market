"""POST /chat — SSE-streamed conversational answer.

Body: { "message": "..." }
Stream events (SSE `data:` JSON):
  {"type":"intent",       "intent":"...", "ticker":"..."}
  {"type":"tool_call",    "name":"...", "args":{...}}
  {"type":"tool_result",  "name":"...", "ms":N, "summary":{...}}
  {"type":"delta",        "text":"..."}
  {"type":"done",         "message":"<full>", "tool_results":{...}, "blocked":bool}
  {"type":"error",        "message":"..."}
"""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.db.models.chat_audit import ChatAudit
from app.db.session import get_session
from app.llm.orchestrator import run_chat

router = APIRouter(tags=["chat"])


class ChatPayload(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None


@router.post("/chat")
async def chat(
    payload: ChatPayload,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> EventSourceResponse:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="redis unavailable")

    settings = get_settings()

    async def event_stream():
        started = time.perf_counter()
        intent_meta: dict[str, Any] = {}
        tool_results: dict[str, Any] = {}
        final_message = ""
        blocked = False
        error_message: str | None = None

        try:
            async for ev in run_chat(payload.message, session=session, redis=redis):
                # Mirror every event to the client as one SSE message.
                yield {"event": ev.get("type", "delta"), "data": json.dumps(ev)}

                t = ev.get("type")
                if t == "intent":
                    intent_meta = {
                        "intent": ev.get("intent"),
                        "ticker": ev.get("ticker"),
                    }
                elif t == "tool_result":
                    tool_results.setdefault(ev["name"], []).append(ev.get("summary"))
                elif t == "done":
                    final_message = ev.get("message", "") or ""
                    blocked = bool(ev.get("blocked", False))
                elif t == "error":
                    error_message = ev.get("message")
        except Exception as e:  # noqa: BLE001
            error_message = f"orchestrator crashed: {e!s}"
            yield {
                "event": "error",
                "data": json.dumps({"type": "error", "message": error_message}),
            }

        # ---- Audit log (write outside the stream loop) -----------------------
        try:
            duration_ms = int((time.perf_counter() - started) * 1000)
            session.add(
                ChatAudit(
                    user_id=payload.user_id,
                    query=payload.message,
                    intent=intent_meta.get("intent"),
                    retrieved={
                        "ticker": intent_meta.get("ticker"),
                        "tool_results": tool_results,
                    },
                    model=settings.openai_model_work,
                    output=final_message or error_message,
                    blocked=blocked,
                    flagged={"error": error_message} if error_message else None,
                    latency_ms=duration_ms,
                )
            )
            await session.commit()
        except Exception:  # noqa: BLE001
            await session.rollback()

    return EventSourceResponse(event_stream())
