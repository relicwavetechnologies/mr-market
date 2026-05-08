from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

import app.llm.context as context_mod
from app.db.models.message import Message
from app.llm.context import build_history_messages, estimate_tokens


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expiry: dict[str, int] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.values[key] = value
        if ex is not None:
            self.expiry[key] = ex
        return True


class FakeClient:
    def __init__(self, summary: str = "User discussed RELIANCE RSI near 62.") -> None:
        self.summary = summary
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.summary),
                )
            ]
        )


def _message(role: str, content: str, *, tool_events=None) -> Message:
    return Message(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        role=role,
        content=content,
        tool_events=tool_events,
    )


def test_estimate_tokens_uses_rough_four_char_rule() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcdefgh") == 2


@pytest.mark.asyncio
async def test_build_history_excludes_current_user_and_reconstructs_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid.uuid4()
    messages = [
        _message("user", "price of Reliance"),
        _message(
            "assistant",
            "Reliance is at 2900.",
            tool_events=[
                {
                    "name": "get_quote",
                    "args": {"ticker": "RELIANCE"},
                    "summary": {"ticker": "RELIANCE", "price": 2900},
                }
            ],
        ),
        _message("user", "and what about its technicals?"),
    ]

    async def fake_load_messages(_conversation_id, *, session):
        return messages

    monkeypatch.setattr(context_mod, "_load_messages", fake_load_messages)

    rendered, info = await build_history_messages(
        conversation_id,
        session=object(),
        redis=FakeRedis(),
        current_message="and what about its technicals?",
        system_tokens=10,
    )

    assert rendered[0] == {"role": "user", "content": "price of Reliance"}
    assert rendered[1]["role"] == "assistant"
    assert rendered[1]["tool_calls"][0]["function"]["name"] == "get_quote"
    assert rendered[2]["role"] == "tool"
    assert "2900" in rendered[2]["content"]
    assert rendered[3] == {"role": "assistant", "content": "Reliance is at 2900."}
    assert "and what about its technicals?" not in str(rendered)
    assert info.recent_turns == 1
    assert info.current_msg_tokens > 0


@pytest.mark.asyncio
async def test_build_history_compacts_older_messages_when_over_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid.uuid4()
    messages = [
        _message("user", f"question {ix} about RELIANCE with long context " * 8)
        for ix in range(12)
    ]
    redis = FakeRedis()
    client = FakeClient()

    async def fake_load_messages(_conversation_id, *, session):
        return messages

    monkeypatch.setattr(context_mod, "_load_messages", fake_load_messages)

    rendered, info = await build_history_messages(
        conversation_id,
        session=object(),
        redis=redis,
        budget_tokens=50,
        client=client,
        model="gpt-test",
    )

    assert client.calls == 1
    assert rendered[0]["role"] == "system"
    assert rendered[0]["content"].startswith("CONVERSATION HISTORY")
    assert "RELIANCE RSI" in rendered[0]["content"]
    assert info.history_compacted is True
    assert info.older_turns == 1
    assert redis.expiry[f"ctx:compact:{conversation_id}:v1"] == 86_400


@pytest.mark.asyncio
async def test_build_history_uses_cached_compaction_without_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid.uuid4()
    messages = [_message("user", f"q{ix}") for ix in range(12)]
    redis = FakeRedis()
    await redis.set(f"ctx:compact:{conversation_id}:v1", "Cached summary")
    client = FakeClient()

    async def fake_load_messages(_conversation_id, *, session):
        return messages

    monkeypatch.setattr(context_mod, "_load_messages", fake_load_messages)

    rendered, info = await build_history_messages(
        conversation_id,
        session=object(),
        redis=redis,
        budget_tokens=50,
        client=client,
        model="gpt-test",
    )

    assert client.calls == 0
    assert (
        rendered[0]["content"] == "CONVERSATION HISTORY (summarized):\nCached summary"
    )
    assert info.history_compacted is True
