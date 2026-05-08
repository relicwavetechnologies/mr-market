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

import asyncio
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user_optional
from app.config import get_settings
from app.db.models.conversation import Conversation
from app.db.models.chat_audit import ChatAudit
from app.db.models.message import Message
from app.db.models.user import User
from app.db.session import get_session
from app.llm.auth import load_state
from app.llm.memory import memory_service
from app.llm.orchestrator import run_chat

router = APIRouter(tags=["chat"])
log = structlog.get_logger(__name__)


class ChatPayload(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None
    conversation_id: uuid.UUID | None = None


@router.post("/chat")
async def chat(
    payload: ChatPayload,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user_optional),
) -> EventSourceResponse:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="redis unavailable")

    settings = get_settings()
    conversation: Conversation | None = None
    if current_user is not None:
        conversation = await _prepare_conversation(
            payload, current_user=current_user, session=session
        )

    async def event_stream():
        started = time.perf_counter()
        request_id = uuid.uuid4().hex[:12]
        intent_meta: dict[str, Any] = {}
        tool_results: dict[str, Any] = {}
        tool_events: list[dict[str, Any]] = []
        recalled_facts: list[str] = []
        memory_status: dict[str, Any] | None = None
        final_message = ""
        blocked = False
        error_message: str | None = None
        guardrail_meta: dict[str, Any] | None = None
        model_name = settings.openai_model_work
        user_id = str(current_user.id) if current_user is not None else None

        log.info(
            "chat_stream_start",
            request_id=request_id,
            authenticated=current_user is not None,
            user_id=user_id,
            conversation_id=str(conversation.id) if conversation is not None else None,
            message_len=len(payload.message),
        )

        if conversation is not None:
            yield {
                "event": "conversation",
                "data": json.dumps(
                    {"type": "conversation", "conversation_id": str(conversation.id)}
                ),
            }

        try:
            async for ev in run_chat(
                payload.message,
                session=session,
                redis=redis,
                user_id=str(current_user.id) if current_user is not None else None,
                risk_profile=getattr(current_user, "risk_profile", None)
                if current_user is not None
                else None,
                conversation_id=conversation.id if conversation is not None else None,
            ):
                t = ev.get("type")
                if t == "memory":
                    recalled_facts = [
                        str(fact) for fact in (ev.get("facts") or []) if fact
                    ]
                    log.info(
                        "chat_memory_recalled",
                        request_id=request_id,
                        count=len(recalled_facts),
                    )
                    continue

                # Mirror public events to the client as one SSE message.
                yield {"event": ev.get("type", "delta"), "data": json.dumps(ev)}

                if t == "auth":
                    model_name = str(ev.get("model") or model_name)
                    log.info(
                        "chat_auth_ready",
                        request_id=request_id,
                        source=ev.get("source"),
                        model=model_name,
                        using_fallback=ev.get("using_fallback"),
                    )
                elif t == "intent":
                    intent_meta = {
                        "intent": ev.get("intent"),
                        "ticker": ev.get("ticker"),
                    }
                    log.info(
                        "chat_intent",
                        request_id=request_id,
                        intent=intent_meta.get("intent"),
                        ticker=intent_meta.get("ticker"),
                    )
                elif t == "memory_status":
                    memory_status = {k: v for k, v in ev.items() if k != "type"}
                    log.info(
                        "chat_memory_status",
                        request_id=request_id,
                        **memory_status,
                    )
                elif t == "tool_call":
                    log.info(
                        "chat_tool_call",
                        request_id=request_id,
                        name=ev.get("name"),
                    )
                    tool_events.append(
                        {
                            "name": ev.get("name"),
                            "status": "running",
                            "args": ev.get("args") or {},
                        }
                    )
                elif t == "tool_result":
                    log.info(
                        "chat_tool_result",
                        request_id=request_id,
                        name=ev.get("name"),
                        ms=ev.get("ms"),
                        summary=ev.get("summary"),
                    )
                    tool_results.setdefault(ev["name"], []).append(ev.get("summary"))
                    for item in reversed(tool_events):
                        if (
                            item.get("name") == ev.get("name")
                            and item.get("status") == "running"
                        ):
                            item.update(
                                {
                                    "status": "done",
                                    "ms": ev.get("ms"),
                                    "summary": ev.get("summary"),
                                }
                            )
                            break
                    else:
                        tool_events.append(
                            {
                                "name": ev.get("name"),
                                "status": "done",
                                "ms": ev.get("ms"),
                                "summary": ev.get("summary"),
                            }
                        )
                elif t == "guardrail":
                    guardrail_meta = {k: v for k, v in ev.items() if k != "type"}
                elif t == "done":
                    final_message = ev.get("message", "") or ""
                    blocked = bool(ev.get("blocked", False))
                elif t == "error":
                    error_message = ev.get("message")
                    log.warning(
                        "chat_stream_error_event",
                        request_id=request_id,
                        error=error_message,
                    )
        except Exception as e:  # noqa: BLE001
            error_message = f"orchestrator crashed: {e!s}"
            log.exception(
                "chat_stream_exception",
                request_id=request_id,
                error=str(e),
            )
            yield {
                "event": "error",
                "data": json.dumps({"type": "error", "message": error_message}),
            }

        # ---- Audit log (write outside the stream loop) -----------------------
        try:
            duration_ms = int((time.perf_counter() - started) * 1000)
            flagged_payload: dict[str, Any] = {}
            if error_message:
                flagged_payload["error"] = error_message
            if guardrail_meta:
                # Only include non-empty guardrail signals to keep the row tidy.
                gr_min = {
                    k: v
                    for k, v in guardrail_meta.items()
                    if (isinstance(v, (list, dict)) and v)
                    or (isinstance(v, bool) and v)
                }
                if gr_min:
                    flagged_payload["guardrail"] = gr_min
            if conversation is not None:
                conversation.updated_at = datetime.now(UTC)
                session.add(
                    Message(
                        conversation_id=conversation.id,
                        role="assistant",
                        content=final_message or error_message or "",
                        sources=_sources_from_tool_results(tool_results),
                        tool_events=tool_events or None,
                        intent=intent_meta.get("intent"),
                        ticker=intent_meta.get("ticker"),
                        blocked=blocked,
                        completion_time_ms=duration_ms,
                    )
                )
            session.add(
                ChatAudit(
                    user_id=str(current_user.id) if current_user is not None else None,
                    query=payload.message,
                    intent=intent_meta.get("intent"),
                    retrieved={
                        "ticker": intent_meta.get("ticker"),
                        "tool_results": tool_results,
                        "memory": memory_status,
                    },
                    model=model_name,
                    output=final_message or error_message,
                    blocked=blocked,
                    flagged=flagged_payload or None,
                    latency_ms=duration_ms,
                )
            )
            await session.commit()
            log.info(
                "chat_stream_done",
                request_id=request_id,
                model=model_name,
                intent=intent_meta.get("intent"),
                ticker=intent_meta.get("ticker"),
                blocked=blocked,
                error=error_message,
                latency_ms=duration_ms,
                tools=list(tool_results.keys()),
            )
            if current_user is not None and not error_message:
                auth = await load_state(redis)
                asyncio.create_task(
                    memory_service.add(
                        str(current_user.id),
                        text=payload.message,
                        api_key=auth.api_key if auth.configured else None,
                        redis=redis,
                        recalled_facts=recalled_facts,
                        blocked=blocked,
                        assistant_text=final_message,
                    )
                )
        except Exception:  # noqa: BLE001
            await session.rollback()
            log.exception("chat_audit_write_failed", request_id=request_id)

    return EventSourceResponse(event_stream())


async def _prepare_conversation(
    payload: ChatPayload,
    *,
    current_user: User,
    session: AsyncSession,
) -> Conversation:
    if payload.conversation_id is not None:
        conversation = await session.get(Conversation, payload.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        if conversation.user_id != current_user.id:
            raise HTTPException(
                status_code=403, detail="conversation belongs to another user"
            )
    else:
        conversation = Conversation(
            user_id=current_user.id, title=_title_from_message(payload.message)
        )
        session.add(conversation)
        await session.flush()

    conversation.updated_at = datetime.now(UTC)
    session.add(
        Message(
            conversation_id=conversation.id,
            role="user",
            content=payload.message,
        )
    )
    await session.commit()
    await session.refresh(conversation)
    return conversation


def _title_from_message(message: str) -> str:
    title = " ".join(message.strip().split())
    if not title:
        return "New Chat"
    if len(title) <= 40:
        return title
    return title[:37] + "..."


def _sources_from_tool_results(
    tool_results: dict[str, Any],
) -> list[dict[str, str]] | None:
    sources: list[dict[str, str]] = []
    for name, summaries in tool_results.items():
        for summary in summaries or []:
            if not isinstance(summary, dict):
                continue
            ticker = str(summary.get("ticker") or name)
            if name == "get_quote":
                confidence = str(summary.get("confidence") or "?")
                ok_sources = summary.get("ok_sources") or []
                sources.append(
                    {
                        "title": f"{ticker} — {confidence} confidence ({len(ok_sources)} sources)",
                        "domain": "midas",
                    }
                )
            elif name == "get_news":
                count = int(summary.get("count") or 0)
                suffix = "" if count == 1 else "s"
                sources.append(
                    {
                        "title": f"{ticker} — {count} headline{suffix} (24h)",
                        "domain": "midas",
                    }
                )
            elif name == "get_company_info":
                sources.append(
                    {
                        "title": f"{ticker} — fundamentals (yfinance + Screener)",
                        "domain": "midas",
                    }
                )
            elif name in {"get_technicals", "get_levels", "get_holding"}:
                label = name.replace("get_", "").replace("_", " ")
                sources.append({"title": f"{ticker} — {label}", "domain": "midas"})
    return sources or None
