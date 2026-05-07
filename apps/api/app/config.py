"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Mr. Market API.

    All values are read from environment variables or a .env file.
    Prefix ``MR_MARKET_`` is stripped automatically, so the env var
    ``MR_MARKET_DATABASE_URL`` maps to ``DATABASE_URL``.
    """

    model_config = SettingsConfigDict(
        env_prefix="MR_MARKET_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # -- Database ---------------------------------------------------------------
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/mrmarket"

    # -- Redis ------------------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"

    # -- LLM providers ----------------------------------------------------------
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    LLM_MODEL: str = "gemini-2.5-flash"

    # -- Qdrant -----------------------------------------------------------------
    QDRANT_URL: str = "http://localhost:6333"

    # -- Security / Auth --------------------------------------------------------
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 60 * 24  # 24 hours

    # -- Application ------------------------------------------------------------
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    LOG_LEVEL: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()
