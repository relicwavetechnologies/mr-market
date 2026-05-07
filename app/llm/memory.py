"""Self-hosted mem0 memory wrapper for Midas personalization.

The wrapper keeps mem0 optional and isolated. Chat should continue to work if
memory is disabled, the Pinecone index is not ready, or extraction fails.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from redis import asyncio as aioredis

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

GREETING_RE = re.compile(r"^\s*(hi|hello|hey|thanks|thank you|thx|ok|okay|sup)\b", re.I)
SAFE_PINECONE_INDEX_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,43}$")
MEMORY_RECALL_RE = re.compile(
    r"\b("
    r"my preferences|saved preferences|saved memory|remember about me|"
    r"what do you remember|do you remember|what do you know about me|"
    r"my style|my watchlist|my risk|my holding period"
    r")\b",
    re.I,
)
MARKET_CAP_RECALL_RE = re.compile(
    r"\b("
    r"do\s+i\s+(prefer|like|track|favor)|"
    r"did\s+i\s+(prefer|like|track|favor)|"
    r"what\s+(is|are)\s+my|"
    r"which\s+market[\s-]?cap"
    r")\b.*\b(big[\s-]?cap|large[\s-]?cap|mid[\s-]?cap|small[\s-]?cap)\b",
    re.I,
)

MAX_SUMMARY_FACTS = 10

_MARKET_CAP_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "big_cap": (
        re.compile(r"\bbig[\s-]?cap\b", re.I),
        re.compile(r"\blarge[\s-]?cap\b", re.I),
        re.compile(r"\bblue[\s-]?chip\b", re.I),
    ),
    "mid_cap": (
        re.compile(r"\bmid[\s-]?cap\b", re.I),
        re.compile(r"\bmedium[\s-]?cap\b", re.I),
    ),
    "small_cap": (
        re.compile(r"\bsmall[\s-]?cap\b", re.I),
        re.compile(r"\bsmallcap\b", re.I),
    ),
}

_SECTOR_ALIASES: dict[str, tuple[str, ...]] = {
    "it": ("information technology", "it", "tech", "technology", "software"),
    "banks": ("banks", "banking", "private bank", "private banks", "bank"),
    "pharma": ("pharma", "pharmaceutical", "pharmaceuticals", "healthcare"),
    "fmcg": ("fmcg", "consumer staples", "staples"),
    "auto": ("auto", "automobile", "automobiles"),
    "financials": ("financials", "nbfc", "nbfcs", "finance", "fintech"),
    "energy": ("energy", "oil", "gas", "power", "utilities"),
    "metals": ("metal", "metals", "mining", "steel"),
    "telecom": ("telecom", "telecommunications"),
    "infra": ("infrastructure", "infra", "capital goods"),
}

MEMORY_EXTRACTION_INSTRUCTIONS = """
Extract only durable user personalization facts useful for future Midas analyst
answers. Keep facts short and concrete.

Store:
- preferred sectors, tickers, watchlists, portfolios, or comparison sets
- risk tolerance, holding horizon, style preferences, and alert preferences
- named constraints like dividend focus, liquidity preference, or avoid lists

Do not store:
- one-off market questions, current prices, transient ticker mentions, greetings,
  refusals, or data returned by Midas tools
- any fact that is merely recalled from existing memory context
"""


@dataclass(frozen=True)
class MemoryHit:
    id: str
    text: str
    score: float | None = None
    metadata: dict[str, Any] | None = None


def should_extract_memory(
    text: str,
    *,
    blocked: bool = False,
    assistant_text: str | None = None,
) -> bool:
    """Return whether a user turn is salient enough to send to mem0."""
    stripped = " ".join(text.strip().split())
    if blocked:
        return False
    if len(stripped) < 12:
        return False
    if stripped.startswith("/"):
        return False
    if GREETING_RE.match(stripped):
        return False
    if looks_like_memory_recall_query(stripped):
        return False
    if assistant_text is not None and len(assistant_text.strip()) < 20:
        return False
    return True


def strip_recalled_facts(text: str, recalled_facts: list[str] | None) -> str:
    """Remove recalled memory snippets before extraction to avoid feedback loops."""
    cleaned = text
    for fact in recalled_facts or []:
        fact = fact.strip()
        if not fact:
            continue
        cleaned = re.sub(re.escape(fact), "", cleaned, flags=re.I)
    return " ".join(cleaned.split())


def looks_like_memory_recall_query(text: str) -> bool:
    normalized = " ".join(text.strip().split())
    return bool(
        MEMORY_RECALL_RE.search(normalized) or MARKET_CAP_RECALL_RE.search(normalized)
    )


def build_memory_block(
    summary: dict[str, Any] | None,
    hits: list[MemoryHit],
) -> str:
    """Build the variable system block injected after the core prompt."""
    lines = [
        "MEMORY CONTEXT (durable user preferences from prior Midas turns):",
        "Use these only when relevant. Do not mention that you used memory.",
    ]

    prefs = (summary or {}).get("preferences") or {}
    market_caps = _coerce_str_list(prefs.get("market_cap"))
    if market_caps:
        lines.append(
            f"- Market-cap preference: {', '.join(_humanise_market_cap(v) for v in market_caps)}"
        )
    if prefs.get("risk_style"):
        lines.append(f"- Risk style: {prefs['risk_style']}")
    if prefs.get("holding_horizon"):
        lines.append(f"- Holding horizon: {prefs['holding_horizon']}")
    sectors = _coerce_str_list(prefs.get("preferred_sectors"))
    if sectors:
        lines.append(f"- Preferred sectors: {', '.join(sectors)}")
    watchlists = _coerce_str_list(prefs.get("watchlists"))
    if watchlists:
        lines.append(f"- Watchlists: {', '.join(watchlists)}")
    avoid = _coerce_str_list(prefs.get("avoid"))
    if avoid:
        lines.append(f"- Avoid list: {', '.join(avoid)}")
    alerts = _coerce_str_list(prefs.get("alerts"))
    if alerts:
        lines.append(f"- Alert preferences: {', '.join(alerts)}")

    seen = set()
    for fact in _coerce_str_list((summary or {}).get("facts")):
        if fact not in seen:
            lines.append(f"- Fact: {fact}")
            seen.add(fact)
    for hit in hits:
        if hit.text and hit.text not in seen:
            lines.append(f"- Fact: {hit.text}")
            seen.add(hit.text)
    return "\n".join(lines)


def build_memory_recall_answer(
    summary: dict[str, Any] | None,
    hits: list[MemoryHit],
    *,
    unavailable_reason: str | None = None,
) -> str:
    if unavailable_reason is not None:
        return _unavailable_message(unavailable_reason)

    prefs = (summary or {}).get("preferences") or {}
    facts = _coerce_str_list((summary or {}).get("facts"))
    if not summary and not hits:
        return "I don't have any saved investing preferences for you yet."

    lines = ["Here's what I have saved about your investing preferences:"]
    market_caps = _coerce_str_list(prefs.get("market_cap"))
    if market_caps:
        lines.append(
            f"- Market-cap: {', '.join(_humanise_market_cap(v) for v in market_caps)}"
        )
    if prefs.get("risk_style"):
        lines.append(f"- Risk style: {prefs['risk_style']}")
    if prefs.get("holding_horizon"):
        lines.append(f"- Holding horizon: {prefs['holding_horizon']}")
    sectors = _coerce_str_list(prefs.get("preferred_sectors"))
    if sectors:
        lines.append(f"- Preferred sectors: {', '.join(sectors)}")
    watchlists = _coerce_str_list(prefs.get("watchlists"))
    if watchlists:
        lines.append(f"- Watchlists: {', '.join(watchlists)}")
    avoid = _coerce_str_list(prefs.get("avoid"))
    if avoid:
        lines.append(f"- Avoid: {', '.join(avoid)}")
    alerts = _coerce_str_list(prefs.get("alerts"))
    if alerts:
        lines.append(f"- Alerts: {', '.join(alerts)}")

    seen = set(lines)
    extra_facts: list[str] = []
    for fact in facts:
        if fact not in seen:
            extra_facts.append(fact)
            seen.add(fact)
    for hit in hits:
        if hit.text and hit.text not in seen:
            extra_facts.append(hit.text)
            seen.add(hit.text)
    if extra_facts:
        lines.append("- Saved facts: " + "; ".join(extra_facts[:5]))
    return "\n".join(lines)


def coerce_mem0_hits(raw: Any) -> list[MemoryHit]:
    """Normalize mem0 SDK result shapes into MemoryHit objects."""
    if isinstance(raw, dict):
        items = raw.get("results") or []
    elif isinstance(raw, list):
        items = raw
    else:
        items = []

    hits: list[MemoryHit] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(
            item.get("memory") or item.get("text") or item.get("data") or ""
        ).strip()
        memory_id = str(item.get("id") or "").strip()
        if not text or not memory_id:
            continue
        score_raw = item.get("score")
        try:
            score = float(score_raw) if score_raw is not None else None
        except (TypeError, ValueError):
            score = None
        metadata = (
            item.get("metadata") if isinstance(item.get("metadata"), dict) else None
        )
        hits.append(MemoryHit(id=memory_id, text=text, score=score, metadata=metadata))
    return hits


def build_memory_summary(hits: list[MemoryHit], *, version: int) -> dict[str, Any]:
    prefs = {
        "market_cap": [],
        "risk_style": None,
        "holding_horizon": None,
        "preferred_sectors": [],
        "avoid": [],
        "watchlists": [],
        "alerts": [],
    }
    facts: list[str] = []
    seen_fact_text: set[str] = set()

    for hit in hits:
        text = " ".join(hit.text.strip().split())
        if not text:
            continue
        if text not in seen_fact_text:
            facts.append(text)
            seen_fact_text.add(text)
        lowered = text.lower()

        for market_cap, patterns in _MARKET_CAP_PATTERNS.items():
            if any(p.search(text) for p in patterns):
                _append_unique(prefs["market_cap"], market_cap)

        if re.search(r"\b(conservative|low risk|safe)\b", lowered):
            prefs["risk_style"] = "conservative"
        elif re.search(r"\b(moderate|balanced)\b", lowered):
            prefs["risk_style"] = "moderate"
        elif re.search(r"\b(aggressive|high risk|risky)\b", lowered):
            prefs["risk_style"] = "aggressive"

        if re.search(r"\b(intraday|day trade)\b", lowered):
            prefs["holding_horizon"] = "intraday"
        elif re.search(r"\b(swing)\b", lowered):
            prefs["holding_horizon"] = "swing"
        elif re.search(r"\b(short[\s-]?term|few weeks|few months)\b", lowered):
            prefs["holding_horizon"] = "short_term"
        elif re.search(r"\b(long[\s-]?term|long term|years?)\b", lowered):
            prefs["holding_horizon"] = "long_term"

        for sector, aliases in _SECTOR_ALIASES.items():
            if any(re.search(rf"\b{re.escape(alias)}\b", lowered) for alias in aliases):
                _append_unique(prefs["preferred_sectors"], sector)

        for match in re.finditer(
            r"\bwatchlist(?:\s+includes|\s*:)?\s+([a-z0-9,&\-\s]+)", lowered
        ):
            for token in _split_simple_list(match.group(1)):
                _append_unique(prefs["watchlists"], token)

        for match in re.finditer(
            r"\b(?:avoid|exclude|skip)\s+([a-z0-9,&\-\s]+)", lowered
        ):
            for token in _split_simple_list(match.group(1)):
                _append_unique(prefs["avoid"], token)

        for match in re.finditer(
            r"\b(?:alert me|notify me)\s+(?:on|about)?\s*([a-z0-9,&\-\s]+)", lowered
        ):
            for token in _split_simple_list(match.group(1)):
                _append_unique(prefs["alerts"], token)

    return {
        "preferences": prefs,
        "facts": facts[:MAX_SUMMARY_FACTS],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "version": version,
    }


class MemoryService:
    def __init__(self) -> None:
        self._client: Any | None = None
        self._client_key: str | None = None
        self._lock = asyncio.Lock()

    def availability_reason(
        self,
        settings: Settings,
        *,
        api_key: str | None,
        user_id: str | None,
    ) -> str | None:
        if not user_id:
            return "anonymous"
        if not settings.mem0_enabled:
            return "disabled"
        if not api_key:
            return "no_api_key"
        if not settings.pinecone_api_key:
            return "unconfigured"
        return None

    async def search(
        self,
        user_id: str | None,
        query: str,
        *,
        api_key: str | None,
        redis: aioredis.Redis | None = None,
        use_cache: bool = False,
        k: int | None = None,
        min_score: float | None = None,
    ) -> list[MemoryHit]:
        settings = get_settings()
        if (
            self.availability_reason(settings, api_key=api_key, user_id=user_id)
            is not None
        ):
            return []

        cache_key: str | None = None
        if redis is not None and use_cache:
            version = await self.get_version(redis, str(user_id))
            cache_key = _search_key(str(user_id), version, _query_hash(query))
            cached = await redis.get(cache_key)
            if isinstance(cached, str):
                hits = _coerce_cached_hits(cached)
                if hits:
                    return hits

        try:
            client = await self._get_client(settings, api_key=str(api_key))
            raw = await client.search(
                query,
                top_k=k or settings.mem0_max_inject,
                filters={"user_id": str(user_id)},
                threshold=min_score
                if min_score is not None
                else settings.mem0_min_score,
            )
            hits = coerce_mem0_hits(raw)[: settings.mem0_max_inject]
        except Exception as e:  # noqa: BLE001
            logger.warning("mem0 search skipped: %s", e)
            return []

        if redis is not None and use_cache and cache_key is not None:
            try:
                await redis.set(
                    cache_key, _hits_to_json(hits), ex=settings.mem0_search_ttl_s
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("memory search cache write skipped: %s", e)
        return hits

    async def add(
        self,
        user_id: str | None,
        *,
        text: str,
        api_key: str | None,
        redis: aioredis.Redis | None = None,
        recalled_facts: list[str] | None = None,
        blocked: bool = False,
        assistant_text: str | None = None,
    ) -> dict[str, Any] | None:
        settings = get_settings()
        if (
            self.availability_reason(settings, api_key=api_key, user_id=user_id)
            is not None
        ):
            return None
        if not should_extract_memory(
            text, blocked=blocked, assistant_text=assistant_text
        ):
            return None

        extraction_text = strip_recalled_facts(text, recalled_facts)
        if not extraction_text or len(extraction_text) < 12:
            return None

        messages: list[dict[str, str]] = [{"role": "user", "content": extraction_text}]
        if assistant_text:
            messages.append({"role": "assistant", "content": assistant_text[:1200]})

        try:
            client = await self._get_client(settings, api_key=str(api_key))
            saved = await client.add(
                messages,
                user_id=str(user_id),
                infer=True,
                metadata={"source": "chat_turn", "app": "midas"},
                prompt=MEMORY_EXTRACTION_INSTRUCTIONS,
            )
            if redis is not None:
                await self.refresh_summary_cache(
                    str(user_id), redis=redis, api_key=api_key, bump_version=True
                )
            return saved
        except Exception as e:  # noqa: BLE001
            logger.warning("mem0 extraction skipped: %s", e)
            return None

    async def add_explicit(
        self,
        user_id: str | None,
        fact: str,
        *,
        api_key: str | None,
        redis: aioredis.Redis | None = None,
    ) -> dict[str, Any] | None:
        settings = get_settings()
        fact = " ".join(fact.strip().split())
        if (
            self.availability_reason(settings, api_key=api_key, user_id=user_id)
            is not None
            or not fact
        ):
            return None
        try:
            client = await self._get_client(settings, api_key=str(api_key))
            saved = await client.add(
                fact,
                user_id=str(user_id),
                infer=False,
                metadata={"source": "explicit", "app": "midas"},
            )
            if redis is not None:
                await self.refresh_summary_cache(
                    str(user_id), redis=redis, api_key=api_key, bump_version=True
                )
            return saved
        except Exception as e:  # noqa: BLE001
            logger.warning("mem0 explicit add skipped: %s", e)
            return None

    async def delete(
        self,
        user_id: str | None,
        memory_id: str,
        *,
        api_key: str | None,
        redis: aioredis.Redis | None = None,
    ) -> bool:
        settings = get_settings()
        if (
            self.availability_reason(settings, api_key=api_key, user_id=user_id)
            is not None
            or not memory_id
        ):
            return False
        try:
            client = await self._get_client(settings, api_key=str(api_key))
            await client.delete(memory_id)
            if redis is not None:
                await self.refresh_summary_cache(
                    str(user_id), redis=redis, api_key=api_key, bump_version=True
                )
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("mem0 delete skipped: %s", e)
            return False

    async def list(
        self,
        user_id: str | None,
        *,
        api_key: str | None,
        limit: int = 50,
    ) -> list[MemoryHit]:
        settings = get_settings()
        if (
            self.availability_reason(settings, api_key=api_key, user_id=user_id)
            is not None
        ):
            return []
        try:
            client = await self._get_client(settings, api_key=str(api_key))
            raw = await client.get_all(
                filters={"user_id": str(user_id)},
                top_k=max(1, min(limit, 100)),
            )
            return coerce_mem0_hits(raw)
        except Exception as e:  # noqa: BLE001
            logger.warning("mem0 list skipped: %s", e)
            return []

    async def get_summary(
        self,
        user_id: str | None,
        *,
        redis: aioredis.Redis | None,
        api_key: str | None,
    ) -> dict[str, Any] | None:
        settings = get_settings()
        if (
            redis is None
            or self.availability_reason(settings, api_key=api_key, user_id=user_id)
            is not None
            or not user_id
        ):
            return None

        key = _summary_key(user_id)
        try:
            raw = await redis.get(key)
        except Exception as e:  # noqa: BLE001
            logger.warning("memory summary cache read skipped: %s", e)
            raw = None

        if isinstance(raw, str):
            summary = _coerce_summary(raw)
            if summary is not None:
                try:
                    await redis.expire(key, settings.mem0_summary_ttl_s)
                except Exception:  # noqa: BLE001
                    pass
                return summary

        return await self.refresh_summary_cache(
            user_id, redis=redis, api_key=api_key, bump_version=False
        )

    async def refresh_summary_cache(
        self,
        user_id: str,
        *,
        redis: aioredis.Redis,
        api_key: str | None,
        bump_version: bool,
    ) -> dict[str, Any] | None:
        settings = get_settings()
        if (
            self.availability_reason(settings, api_key=api_key, user_id=user_id)
            is not None
        ):
            return None

        version = (
            await self.bump_version(redis, user_id)
            if bump_version
            else await self.get_version(redis, user_id)
        )
        hits = await self.list(user_id, api_key=api_key, limit=100)
        try:
            if not hits:
                await redis.delete(_summary_key(user_id))
                return None
            summary = build_memory_summary(hits, version=version)
            await redis.set(
                _summary_key(user_id),
                json.dumps(summary),
                ex=settings.mem0_summary_ttl_s,
            )
            return summary
        except Exception as e:  # noqa: BLE001
            logger.warning("memory summary cache write skipped: %s", e)
            return None

    async def get_version(self, redis: aioredis.Redis, user_id: str) -> int:
        try:
            raw = await redis.get(_version_key(user_id))
        except Exception as e:  # noqa: BLE001
            logger.warning("memory version read skipped: %s", e)
            return 0
        if raw is None:
            return 0
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    async def bump_version(self, redis: aioredis.Redis, user_id: str) -> int:
        try:
            return int(await redis.incr(_version_key(user_id)))
        except Exception as e:  # noqa: BLE001
            logger.warning("memory version bump skipped: %s", e)
            return await self.get_version(redis, user_id) + 1

    async def _get_client(self, settings: Settings, *, api_key: str) -> Any:
        client_key = self._client_fingerprint(settings, api_key=api_key)
        if self._client is not None and self._client_key == client_key:
            return self._client

        async with self._lock:
            if self._client is not None and self._client_key == client_key:
                return self._client
            self._validate_pinecone_index(settings.pinecone_index_name)
            Path(settings.mem0_history_db_path).parent.mkdir(
                parents=True, exist_ok=True
            )
            config = {
                "vector_store": {
                    "provider": "pinecone",
                    "config": {
                        "api_key": settings.pinecone_api_key,
                        "collection_name": settings.pinecone_index_name,
                        "embedding_model_dims": settings.mem0_embedding_dims,
                        "serverless_config": {
                            "cloud": settings.pinecone_cloud,
                            "region": settings.pinecone_region,
                        },
                        "namespace": settings.pinecone_namespace or None,
                        "metric": settings.pinecone_metric,
                        "hybrid_search": False,
                        "batch_size": 100,
                    },
                },
                "embedder": {
                    "provider": "openai",
                    "config": {
                        "api_key": api_key,
                        "model": settings.mem0_embedding_model,
                        "embedding_dims": settings.mem0_embedding_dims,
                    },
                },
                "llm": {
                    "provider": "openai",
                    "config": {
                        "api_key": api_key,
                        "model": settings.openai_model_work,
                        "temperature": 0.1,
                        "max_tokens": 800,
                    },
                },
                "history_db_path": settings.mem0_history_db_path,
                "custom_instructions": MEMORY_EXTRACTION_INSTRUCTIONS,
            }
            try:
                from mem0 import AsyncMemory
            except ImportError as e:
                raise RuntimeError("mem0ai is not installed") from e

            self._client = AsyncMemory.from_config(config)
            self._client_key = client_key
            return self._client

    def _client_fingerprint(self, settings: Settings, *, api_key: str) -> str:
        raw = "|".join(
            [
                api_key,
                settings.pinecone_api_key,
                settings.pinecone_index_name,
                settings.pinecone_cloud,
                settings.pinecone_region,
                settings.pinecone_namespace,
                settings.pinecone_metric,
                settings.mem0_embedding_model,
                str(settings.mem0_embedding_dims),
                settings.openai_model_work,
            ]
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def _validate_pinecone_index(self, index_name: str) -> None:
        if not SAFE_PINECONE_INDEX_RE.match(index_name):
            raise ValueError(
                "PINECONE_INDEX_NAME must be lowercase letters, numbers, and hyphens"
            )


def _summary_key(user_id: str) -> str:
    return f"memory:summary:{user_id}"


def _version_key(user_id: str) -> str:
    return f"memory:version:{user_id}"


def _search_key(user_id: str, version: int, query_hash: str) -> str:
    return f"memory:search:{user_id}:{version}:{query_hash}"


def _query_hash(query: str) -> str:
    normalized = re.sub(r"\s+", " ", query.strip().lower())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _hits_to_json(hits: list[MemoryHit]) -> str:
    payload = [
        {"id": hit.id, "memory": hit.text, "score": hit.score, "metadata": hit.metadata}
        for hit in hits
    ]
    return json.dumps(payload)


def _coerce_cached_hits(raw: str) -> list[MemoryHit]:
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return coerce_mem0_hits(payload)


def _coerce_summary(raw: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    preferences = payload.get("preferences")
    facts = payload.get("facts")
    if not isinstance(preferences, dict) or not isinstance(facts, list):
        return None
    return {
        "preferences": {
            "market_cap": _coerce_str_list(preferences.get("market_cap")),
            "risk_style": preferences.get("risk_style"),
            "holding_horizon": preferences.get("holding_horizon"),
            "preferred_sectors": _coerce_str_list(preferences.get("preferred_sectors")),
            "avoid": _coerce_str_list(preferences.get("avoid")),
            "watchlists": _coerce_str_list(preferences.get("watchlists")),
            "alerts": _coerce_str_list(preferences.get("alerts")),
        },
        "facts": _coerce_str_list(facts),
        "updated_at": payload.get("updated_at"),
        "version": int(payload.get("version") or 0),
    }


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _coerce_str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        text = str(item).strip()
        if text and text not in out:
            out.append(text)
    return out


def _split_simple_list(raw: str) -> list[str]:
    trimmed = raw.strip(" .,:;")
    if not trimmed:
        return []
    parts = re.split(r",|/|\band\b", trimmed)
    return [p.strip(" .,:;") for p in parts if p.strip(" .,:;")]


def _humanise_market_cap(value: str) -> str:
    return {
        "big_cap": "big-cap",
        "mid_cap": "mid-cap",
        "small_cap": "small-cap",
    }.get(value, value.replace("_", " "))


def _unavailable_message(reason: str) -> str:
    if reason == "anonymous":
        return "I can't access saved preferences in this chat because you're not signed in."
    if reason == "disabled":
        return "Memory is disabled in this environment right now."
    if reason == "unconfigured":
        return "Memory is not configured in this environment right now."
    if reason == "no_api_key":
        return (
            "Memory is temporarily unavailable because the LLM credential is missing."
        )
    return "Memory is unavailable right now."


memory_service = MemoryService()
