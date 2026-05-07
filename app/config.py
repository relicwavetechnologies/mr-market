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

    # Reserved for later swap (Anthropic / Gemini).
    anthropic_api_key: str = ""
    gemini_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
