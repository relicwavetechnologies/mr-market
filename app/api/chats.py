from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import get_settings
from app.db.models.conversation import Conversation
from app.db.models.message import Message
from app.db.models.user import User
from app.db.session import get_session
from app.llm.auth import AuthState, effective_models, load_state
from app.llm.codex_client import CodexOpenAIClient
from app.llm.context import ContextInfo, build_history_messages, estimate_tokens
from app.llm.prompts import SYSTEM_PROMPT

router = APIRouter(prefix="/api/chats", tags=["chats"])


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    sources: list[dict[str, Any]] | None = None
    tool_events: list[dict[str, Any]] | None = None
    intent: str | None = None
    ticker: str | None = None
    blocked: bool = False
    completion_time_ms: int | None = None
    created_at: datetime

    @classmethod
    def from_model(cls, message: Message) -> "MessageOut":
        return cls(
            id=str(message.id),
            role=message.role,
            content=message.content,
            sources=message.sources,
            tool_events=message.tool_events,
            intent=message.intent,
            ticker=message.ticker,
            blocked=message.blocked,
            completion_time_ms=message.completion_time_ms,
            created_at=message.created_at,
        )


class ConversationOut(BaseModel):
    id: str
    title: str
    last_message: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class CreateConversationPayload(BaseModel):
    title: str = Field(default="New Chat", min_length=1, max_length=160)


class RenameConversationPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)


class ContextInfoOut(BaseModel):
    system_tokens: int
    memory_tokens: int
    history_tokens: int
    history_compacted: bool
    recent_turns: int
    older_turns: int
    current_msg_tokens: int
    total_tokens: int
    budget_tokens: int
    usage_pct: float

    @classmethod
    def from_info(cls, info: ContextInfo) -> "ContextInfoOut":
        return cls(**info.to_dict())


@router.get("", response_model=list[ConversationOut])
async def list_chats(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ConversationOut]:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(desc(Conversation.updated_at))
        .limit(limit)
        .offset(offset)
    )
    conversations = list(result.scalars())
    return [await _conversation_out(c, session=session) for c in conversations]


@router.post("", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
async def create_chat(
    payload: CreateConversationPayload,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ConversationDetail:
    conversation = Conversation(user_id=current_user.id, title=payload.title.strip())
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return ConversationDetail(
        **(await _conversation_out(conversation, session=session)).model_dump(),
        messages=[],
    )


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_chat(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ConversationDetail:
    conversation = await _get_conversation(
        conversation_id, current_user=current_user, session=session
    )
    messages = await _messages_for(conversation.id, session=session)
    return ConversationDetail(
        **(await _conversation_out(conversation, session=session)).model_dump(),
        messages=[MessageOut.from_model(m) for m in messages],
    )


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def rename_chat(
    conversation_id: uuid.UUID,
    payload: RenameConversationPayload,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ConversationOut:
    conversation = await _get_conversation(
        conversation_id, current_user=current_user, session=session
    )
    conversation.title = payload.title.strip()
    await session.commit()
    await session.refresh(conversation)
    return await _conversation_out(conversation, session=session)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    conversation = await _get_conversation(
        conversation_id, current_user=current_user, session=session
    )
    await session.delete(conversation)
    await session.commit()


@router.get("/{conversation_id}/context-info", response_model=ContextInfoOut)
async def get_context_info(
    conversation_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ContextInfoOut:
    conversation = await _get_conversation(
        conversation_id, current_user=current_user, session=session
    )
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="redis unavailable")

    _, info = await build_history_messages(
        conversation.id,
        session=session,
        redis=redis,
        system_tokens=estimate_tokens(SYSTEM_PROMPT),
    )
    return ContextInfoOut.from_info(info)


@router.post("/{conversation_id}/compact", response_model=ContextInfoOut)
async def compact_chat_context(
    conversation_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ContextInfoOut:
    conversation = await _get_conversation(
        conversation_id, current_user=current_user, session=session
    )
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="redis unavailable")

    auth = await load_state(redis)
    if not auth.configured or auth.api_key is None:
        raise HTTPException(status_code=503, detail="OpenAI auth is not configured")

    settings = get_settings()
    models = effective_models(auth, settings)
    _, info = await build_history_messages(
        conversation.id,
        session=session,
        redis=redis,
        client=_client(auth),
        model=models.work,
        system_tokens=estimate_tokens(SYSTEM_PROMPT),
        force_compact=True,
    )
    return ContextInfoOut.from_info(info)


async def _get_conversation(
    conversation_id: uuid.UUID,
    *,
    current_user: User,
    session: AsyncSession,
) -> Conversation:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found"
        )
    if conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="conversation belongs to another user",
        )
    return conversation


async def _conversation_out(
    conversation: Conversation, *, session: AsyncSession
) -> ConversationOut:
    latest = await _latest_message(conversation.id, session=session)
    return ConversationOut(
        id=str(conversation.id),
        title=conversation.title,
        last_message=(latest.content[:100] if latest else ""),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


async def _latest_message(
    conversation_id: uuid.UUID, *, session: AsyncSession
) -> Message | None:
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(desc(Message.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _messages_for(
    conversation_id: uuid.UUID, *, session: AsyncSession
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(result.scalars())


def _client(auth: AuthState) -> Any:
    if auth.source in {"codex_oauth", "codex_cli"}:
        return CodexOpenAIClient(auth.api_key or "")
    return AsyncOpenAI(api_key=auth.api_key)
