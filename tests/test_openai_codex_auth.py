from __future__ import annotations

import json

import pytest

import app.llm.auth as auth_mod
from app.config import Settings
from app.llm.auth import (
    REDIS_CODEX_TOKENS,
    complete_codex_login,
    effective_models,
    initiate_codex_login,
    load_state,
)


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

    async def delete(self, key: str):
        self.values.pop(key, None)
        self.expiry.pop(key, None)
        return 1


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/midas",
        sync_database_url="postgresql://user:pass@localhost:5432/midas",
        openai_redirect_uri="http://localhost:1455/auth/callback",
        openai_model_work="gpt-5.4-mini",
        openai_model_router="gpt-5.4-mini",
        openai_fallback_model_work="gpt-4o-mini",
        openai_fallback_model_router="gpt-4o-mini",
    )


@pytest.mark.asyncio
async def test_initiate_codex_login_stores_pkce_and_returns_auth_url(monkeypatch):
    settings = _settings()
    monkeypatch.setattr(auth_mod, "get_settings", lambda: settings)
    redis = FakeRedis()

    started = await initiate_codex_login(redis)

    assert started["redirect_uri"] == settings.openai_redirect_uri
    assert "https://auth.openai.com/oauth/authorize" in started["auth_url"]
    assert "codex_cli_simplified_flow=true" in started["auth_url"]
    assert "code_challenge_method=S256" in started["auth_url"]
    assert any(key.startswith("openai:codex_pkce:") for key in redis.values.keys())


@pytest.mark.asyncio
async def test_complete_codex_login_exchanges_callback_and_prefers_codex_token(
    monkeypatch,
):
    settings = _settings()
    monkeypatch.setattr(auth_mod, "get_settings", lambda: settings)
    redis = FakeRedis()
    started = await initiate_codex_login(redis)
    state = started["state"]

    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {
                "access_token": "codex-access",
                "refresh_token": "codex-refresh",
                "expires_in": 3600,
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            assert url == auth_mod.CODEX_TOKEN_URL
            assert json["client_id"] == auth_mod.CODEX_CLIENT_ID
            assert json["code"] == "abc"
            assert json["redirect_uri"] == settings.openai_redirect_uri
            assert json["grant_type"] == "authorization_code"
            return FakeResponse()

    monkeypatch.setattr(auth_mod.httpx, "AsyncClient", FakeClient)

    await complete_codex_login(
        redis,
        f"{settings.openai_redirect_uri}?code=abc&state={state}",
    )

    stored = json.loads(redis.values[REDIS_CODEX_TOKENS])
    assert stored["access_token"] == "codex-access"
    assert stored["refresh_token"] == "codex-refresh"

    loaded = await load_state(redis)
    assert loaded.source == "codex_oauth"
    assert loaded.api_key == "codex-access"
    assert effective_models(loaded, settings).work == "gpt-5.4-mini"


@pytest.mark.asyncio
async def test_env_key_is_ignored_unless_explicitly_enabled(monkeypatch):
    settings = _settings()
    settings.openai_api_key = "env-key"
    settings.openai_allow_env_credentials = False
    monkeypatch.setattr(auth_mod, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_mod, "_read_codex_auth", lambda: (None, None, None))
    monkeypatch.setenv("OPENAI_API_KEY", "process-env-key")

    unloaded = await load_state(FakeRedis())
    assert unloaded.source == "none"

    settings.openai_allow_env_credentials = True
    loaded = await load_state(FakeRedis())
    assert loaded.source == "env"
    assert loaded.api_key == "env-key"
    models = effective_models(loaded, settings)
    assert models.using_fallback
    assert models.work == "gpt-4o-mini"
    assert "OPENAI_API_KEY" in (models.fallback_reason or "")
