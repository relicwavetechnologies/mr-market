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

    anthropic_api_key: str = ""
    anthropic_model_work: str = "claude-sonnet-4-5"
    anthropic_model_router: str = "claude-haiku-4-5"
    gemini_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
