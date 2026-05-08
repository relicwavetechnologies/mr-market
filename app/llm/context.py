from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from redis import asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.message import Message

RECENT_HISTORY_MESSAGES = 10
COMPACTION_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class ContextInfo:
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // 4) if text else 0


async def build_history_messages(
    conversation_id: uuid.UUID | None,
    *,
    session: AsyncSession,
    redis: aioredis.Redis,
    budget_tokens: int = 100_000,
    current_message: str = "",
    client: Any | None = None,
    model: str | None = None,
    system_tokens: int = 0,
    memory_tokens: int = 0,
    force_compact: bool = False,
    exclude_latest_user_turn: bool = True,
) -> tuple[list[dict[str, Any]], ContextInfo]:
    current_msg_tokens = estimate_tokens(current_message)
    if conversation_id is None:
        info = _info(
            system_tokens=system_tokens,
            memory_tokens=memory_tokens,
            history_tokens=0,
            history_compacted=False,
            recent_turns=0,
            older_turns=0,
            current_msg_tokens=current_msg_tokens,
            budget_tokens=budget_tokens,
        )
        return [], info

    messages = await _load_messages(conversation_id, session=session)
    # The chat endpoint persists the current user turn before calling the
    # orchestrator. Keep it out of the history block because the orchestrator
    # appends the current message separately after history injection.
    if exclude_latest_user_turn and messages and messages[-1].role == "user":
        messages = messages[:-1]

    older = messages[:-RECENT_HISTORY_MESSAGES]
    recent = messages[-RECENT_HISTORY_MESSAGES:]
    rendered: list[dict[str, Any]] = []
    history_compacted = False

    if older:
        cache_key = _cache_key(conversation_id, older)
        cached_summary = await redis.get(cache_key)
        if cached_summary:
            rendered.append(_summary_message(_decode_redis(cached_summary)))
            history_compacted = True
        else:
            older_rendered = _messages_for_llm(older)
            recent_rendered = _messages_for_llm(recent)
            projected_tokens = (
                system_tokens
                + memory_tokens
                + current_msg_tokens
                + _estimate_message_tokens(older_rendered)
                + _estimate_message_tokens(recent_rendered)
            )
            if force_compact and client is not None and model is not None:
                summary = await compact_history(
                    conversation_id,
                    older,
                    redis=redis,
                    client=client,
                    model=model,
                )
                rendered.append(_summary_message(summary))
                history_compacted = True
            elif projected_tokens <= budget_tokens:
                rendered.extend(older_rendered)
            elif client is not None and model is not None:
                summary = await compact_history(
                    conversation_id,
                    older,
                    redis=redis,
                    client=client,
                    model=model,
                )
                rendered.append(_summary_message(summary))
                history_compacted = True
            else:
                # Context-info estimation must not spend an LLM call. Return the
                # verbatim estimate so the UI can show the true pressure.
                rendered.extend(older_rendered)

    rendered.extend(_messages_for_llm(recent))
    history_tokens = _estimate_message_tokens(rendered)
    info = _info(
        system_tokens=system_tokens,
        memory_tokens=memory_tokens,
        history_tokens=history_tokens,
        history_compacted=history_compacted,
        recent_turns=_count_user_turns(recent),
        older_turns=_count_user_turns(older),
        current_msg_tokens=current_msg_tokens,
        budget_tokens=budget_tokens,
    )
    return rendered, info


async def compact_history(
    conversation_id: uuid.UUID,
    older_messages: list[Message],
    *,
    redis: aioredis.Redis,
    client: Any,
    model: str,
) -> str:
    cache_key = _cache_key(conversation_id, older_messages)
    cached = await redis.get(cache_key)
    if cached:
        return _decode_redis(cached)

    transcript = _transcript_for_summary(older_messages)
    if not transcript:
        summary = "No earlier conversation context."
    else:
        try:
            resp = await client.chat.completions.create(
                model=model,
                temperature=0.1,
                max_tokens=260,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Summarize this conversation history for Midas. Preserve "
                            "tickers, prices, RSI values, conclusions, user preferences, "
                            "and unresolved asks. Keep it under 200 words."
                        ),
                    },
                    {"role": "user", "content": transcript},
                ],
            )
            summary = (resp.choices[0].message.content or "").strip()
        except Exception:  # noqa: BLE001
            summary = "Earlier conversation exists; summary unavailable due to transient model error."
        if not summary:
            summary = (
                "Earlier conversation existed, but no useful summary was produced."
            )

    await redis.set(cache_key, summary, ex=COMPACTION_TTL_SECONDS)
    return summary


async def _load_messages(
    conversation_id: uuid.UUID,
    *,
    session: AsyncSession,
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
    )
    return list(result.scalars())


def _messages_for_llm(messages: list[Message]) -> list[dict[str, Any]]:
    rendered: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "user":
            rendered.append({"role": "user", "content": message.content})
            continue

        tool_events = [
            event
            for event in (message.tool_events or [])
            if isinstance(event, dict) and event.get("name")
        ]
        if tool_events:
            tool_calls: list[dict[str, Any]] = []
            tool_messages: list[dict[str, Any]] = []
            for ix, event in enumerate(tool_events):
                call_id = f"hist_{message.id.hex}_{ix}"
                tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": str(event.get("name")),
                            "arguments": _json_dumps(event.get("args") or {}),
                        },
                    }
                )
                tool_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": _json_dumps(event.get("summary") or {}),
                    }
                )
            rendered.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": tool_calls,
                }
            )
            rendered.extend(tool_messages)
            if message.content:
                rendered.append({"role": "assistant", "content": message.content})
            continue

        rendered.append({"role": "assistant", "content": message.content})
    return rendered


def _transcript_for_summary(messages: list[Message]) -> str:
    lines: list[str] = []
    for message in messages:
        role = "User" if message.role == "user" else "Assistant"
        content = " ".join((message.content or "").split())
        if content:
            lines.append(f"{role}: {content}")
        for event in message.tool_events or []:
            if not isinstance(event, dict):
                continue
            summary = event.get("summary")
            if summary:
                lines.append(f"Tool {event.get('name')}: {_json_dumps(summary)[:1200]}")
    return "\n".join(lines)[-60_000:]


def _summary_message(summary: str) -> dict[str, str]:
    return {
        "role": "system",
        "content": f"CONVERSATION HISTORY (summarized):\n{summary}",
    }


def _estimate_message_tokens(messages: list[dict[str, Any]]) -> int:
    return sum(estimate_tokens(_json_dumps(message)) for message in messages)


def _info(
    *,
    system_tokens: int,
    memory_tokens: int,
    history_tokens: int,
    history_compacted: bool,
    recent_turns: int,
    older_turns: int,
    current_msg_tokens: int,
    budget_tokens: int,
) -> ContextInfo:
    total = system_tokens + memory_tokens + history_tokens + current_msg_tokens
    usage = round((total / budget_tokens) * 100, 1) if budget_tokens else 0.0
    return ContextInfo(
        system_tokens=system_tokens,
        memory_tokens=memory_tokens,
        history_tokens=history_tokens,
        history_compacted=history_compacted,
        recent_turns=recent_turns,
        older_turns=older_turns,
        current_msg_tokens=current_msg_tokens,
        total_tokens=total,
        budget_tokens=budget_tokens,
        usage_pct=usage,
    )


def _count_user_turns(messages: list[Message]) -> int:
    return sum(1 for message in messages if message.role == "user")


def _cache_key(conversation_id: uuid.UUID, older_messages: list[Message]) -> str:
    fingerprint = "|".join(
        f"{m.id.hex}:{int(m.created_at.timestamp()) if m.created_at else 0}"
        for m in older_messages
    )
    return f"ctx:compact:{conversation_id}:{hash(fingerprint)}"


def _decode_redis(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, default=str, separators=(",", ":"))
