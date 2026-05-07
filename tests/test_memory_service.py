from __future__ import annotations

from dataclasses import dataclass

import pytest

import app.llm.memory as memory_mod
from app.config import Settings
from app.llm.memory import (
    MemoryHit,
    MemoryService,
    build_memory_block,
    build_memory_recall_answer,
    build_memory_summary,
    coerce_mem0_hits,
    looks_like_memory_recall_query,
    should_extract_memory,
    strip_recalled_facts,
)
from app.llm.orchestrator import _tool_specs_for_turn


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

    async def expire(self, key: str, seconds: int):
        self.expiry[key] = seconds
        return True

    async def delete(self, key: str):
        self.values.pop(key, None)
        self.expiry.pop(key, None)
        return 1

    async def incr(self, key: str):
        current = int(self.values.get(key, "0"))
        current += 1
        self.values[key] = str(current)
        return current


@dataclass
class FakeClient:
    raw_results: list[dict]
    search_calls: int = 0

    async def search(self, *args, **kwargs):
        self.search_calls += 1
        return self.raw_results


def _settings() -> Settings:
    s = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/midas",
        sync_database_url="postgresql://user:pass@localhost:5432/midas",
    )
    s.mem0_enabled = True
    s.pinecone_api_key = "pinecone-key"
    s.mem0_summary_ttl_s = 100
    s.mem0_search_ttl_s = 50
    return s


def test_salience_filter_skips_low_value_turns() -> None:
    assert not should_extract_memory("hi")
    assert not should_extract_memory("thanks for this")
    assert not should_extract_memory("/remember I like banks")
    assert not should_extract_memory("I like IT", blocked=True)
    assert not should_extract_memory("what are my preferences again?")
    assert not should_extract_memory("I prefer dividend payers", assistant_text="ok")


def test_salience_filter_allows_stable_preference() -> None:
    assert should_extract_memory(
        "I usually track IT and private bank stocks.",
        assistant_text="Noted. I can use that context for future market snapshots.",
    )
    assert should_extract_memory(
        "I prefer big cap companies only.",
        assistant_text="Noted. I can use that preference in future market snapshots.",
    )


def test_memory_recall_query_detection() -> None:
    assert looks_like_memory_recall_query(
        "What do you remember about my saved preferences?"
    )
    assert looks_like_memory_recall_query("Do I prefer big-cap or small-cap companies?")
    assert not looks_like_memory_recall_query("What is the RSI on Reliance today?")
    assert not looks_like_memory_recall_query("I prefer big cap companies only")
    assert not looks_like_memory_recall_query("I prefer mid cap companies too")


def test_remember_tool_is_hidden_when_memory_unavailable() -> None:
    unavailable_names = {
        spec["function"]["name"]
        for spec in _tool_specs_for_turn(memory_available=False)
    }
    available_names = {
        spec["function"]["name"] for spec in _tool_specs_for_turn(memory_available=True)
    }

    assert "remember_fact" not in unavailable_names
    assert "remember_fact" in available_names


def test_strip_recalled_facts_prevents_feedback_loop() -> None:
    cleaned = strip_recalled_facts(
        "I usually track IT and private bank stocks. Also add dividend payers.",
        ["I usually track IT and private bank stocks."],
    )

    assert cleaned == "Also add dividend payers."


def test_coerce_mem0_hits_normalizes_sdk_shape() -> None:
    hits = coerce_mem0_hits(
        {
            "results": [
                {"id": "m1", "memory": "User prefers dividend payers", "score": "0.72"},
                {"id": "m2", "data": "User tracks IT", "score": None},
                {"id": "", "memory": "ignore missing id"},
            ]
        }
    )

    assert [hit.text for hit in hits] == [
        "User prefers dividend payers",
        "User tracks IT",
    ]
    assert hits[0].score == 0.72


def test_build_memory_summary_extracts_structured_preferences() -> None:
    summary = build_memory_summary(
        [
            MemoryHit(id="m1", text="User prefers big cap companies only"),
            MemoryHit(id="m2", text="User tracks IT and private bank stocks"),
            MemoryHit(
                id="m3", text="User is a conservative investor with a long term horizon"
            ),
        ],
        version=7,
    )

    assert summary["preferences"]["market_cap"] == ["big_cap"]
    assert summary["preferences"]["preferred_sectors"] == ["it", "banks"]
    assert summary["preferences"]["risk_style"] == "conservative"
    assert summary["preferences"]["holding_horizon"] == "long_term"
    assert summary["version"] == 7


def test_build_memory_block_includes_summary_and_hits() -> None:
    summary = build_memory_summary(
        [MemoryHit(id="m1", text="User prefers big cap companies only")],
        version=1,
    )
    block = build_memory_block(
        summary,
        [MemoryHit(id="m2", text="User tracks banks")],
    )

    assert block.startswith("MEMORY CONTEXT")
    assert "Market-cap preference: big-cap" in block
    assert "Fact: User prefers big cap companies only" in block
    assert "Fact: User tracks banks" in block


def test_build_memory_recall_answer_handles_unavailable_and_hits() -> None:
    assert "not signed in" in build_memory_recall_answer(
        None, [], unavailable_reason="anonymous"
    )

    summary = build_memory_summary(
        [MemoryHit(id="m1", text="User prefers big cap companies only")],
        version=1,
    )
    answer = build_memory_recall_answer(summary, [])
    assert "saved about your investing preferences" in answer
    assert "Market-cap: big-cap" in answer


def test_memory_service_requires_pinecone_key() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/midas",
        sync_database_url="postgresql://user:pass@localhost:5432/midas",
    )
    settings.mem0_enabled = True
    settings.pinecone_api_key = ""

    service = MemoryService()
    assert (
        service.availability_reason(settings, api_key="openai-key", user_id="u1")
        == "unconfigured"
    )

    settings.pinecone_api_key = "pinecone-key"
    assert (
        service.availability_reason(settings, api_key="openai-key", user_id="u1")
        is None
    )


@pytest.mark.asyncio
async def test_summary_cache_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings()
    monkeypatch.setattr(memory_mod, "get_settings", lambda: settings)

    service = MemoryService()
    redis = FakeRedis()

    async def fake_list(user_id: str | None, *, api_key: str | None, limit: int = 50):
        return [MemoryHit(id="m1", text="User prefers big cap companies only")]

    monkeypatch.setattr(service, "list", fake_list)

    summary = await service.refresh_summary_cache(
        "u1",
        redis=redis,
        api_key="openai-key",
        bump_version=True,
    )
    assert summary is not None
    assert summary["version"] == 1
    assert summary["preferences"]["market_cap"] == ["big_cap"]
    assert redis.expiry["memory:summary:u1"] == settings.mem0_summary_ttl_s

    cached = await service.get_summary("u1", redis=redis, api_key="openai-key")
    assert cached is not None
    assert cached["version"] == 1


@pytest.mark.asyncio
async def test_search_uses_redis_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings()
    monkeypatch.setattr(memory_mod, "get_settings", lambda: settings)

    service = MemoryService()
    redis = FakeRedis()
    await redis.set("memory:version:u1", "2")

    fake_client = FakeClient(
        raw_results=[
            {"id": "m1", "memory": "User prefers big cap companies only", "score": 0.91}
        ]
    )

    async def fake_get_client(_settings: Settings, *, api_key: str):
        return fake_client

    monkeypatch.setattr(service, "_get_client", fake_get_client)

    first = await service.search(
        "u1",
        "what are my preferences",
        api_key="openai-key",
        redis=redis,
        use_cache=True,
    )
    second = await service.search(
        "u1",
        "what are my preferences",
        api_key="openai-key",
        redis=redis,
        use_cache=True,
    )

    assert [hit.text for hit in first] == ["User prefers big cap companies only"]
    assert [hit.text for hit in second] == ["User prefers big cap companies only"]
    assert fake_client.search_calls == 1
