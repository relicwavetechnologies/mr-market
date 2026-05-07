from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "local"
    log_level: str = "INFO"

    database_url: str = Field(...)
    sync_database_url: str = Field(...)
    redis_url: str = "redis://localhost:6379/0"

    # OpenAI is the active LLM provider for Phase 1.
    openai_api_key: str = ""
    openai_model_work: str = "gpt-4o-mini"
    openai_model_router: str = "gpt-4o-mini"

    # Guardrail mode — Phase-2 default is "warn" (internal tool: blocklist
    # hits are logged + UI banner is shown, but the streamed answer is NOT
    # overridden). Set GUARDRAIL_MODE=strict to revert to Phase-1 behaviour.
    guardrail_mode: str = "warn"

    # Vector-store backend for RAG retrieval.
    #   "jsonb"    — Postgres JSONB column + numpy cosine (always available).
    #   "pinecone" — Pinecone managed cloud (requires PINECONE_API_KEY).
    # Auto-falls-back to "jsonb" if backend="pinecone" but the API key is
    # missing — never silently fails a query.
    vector_backend: str = "jsonb"
    pinecone_api_key: str = ""
    pinecone_index_name: str = "mr-market"
    # Pinecone serverless region; only used at index creation time.
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"

    # Reserved for later swap (Anthropic / Gemini).
    anthropic_api_key: str = ""
    gemini_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
