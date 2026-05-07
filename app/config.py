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

    # OpenAI Codex OAuth is the active LLM provider for local demo chat.
    # Env/API-key credentials are fallback-only. Codex OAuth/CLI wins whenever
    # available; fallback mode uses the public OpenAI API with GPT-4o mini.
    openai_api_key: str = ""
    openai_allow_env_credentials: bool = True
    openai_redirect_uri: str = "http://localhost:1455/auth/callback"
    openai_model_work: str = "gpt-5.4-mini"
    openai_model_router: str = "gpt-5.4-mini"
    openai_fallback_model_work: str = "gpt-4o-mini"
    openai_fallback_model_router: str = "gpt-4o-mini"

    # Demo auth. Override JWT_SECRET outside local development.
    jwt_secret: str = "dev-insecure-change-me-32-bytes-minimum"
    jwt_access_ttl_min: int = 15
    jwt_refresh_ttl_days: int = 30

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

    # Personalization memory: mem0 + OpenAI extraction/embeddings + Pinecone.
    # Disabled by default so evals and anonymous demo flows remain deterministic
    # unless the operator opts in.
    mem0_enabled: bool = False
    pinecone_namespace: str = "midas"
    pinecone_metric: str = "cosine"
    mem0_embedding_model: str = "text-embedding-3-small"
    mem0_embedding_dims: int = 1536
    mem0_min_score: float = 0.3
    mem0_max_inject: int = 5
    mem0_history_db_path: str = "data/mem0-history.db"
    mem0_summary_ttl_s: int = 6 * 60 * 60
    mem0_search_ttl_s: int = 60 * 60

    # Reserved for later swap (Anthropic / Gemini).
    anthropic_api_key: str = ""
    gemini_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
