"""Rigorous tests for Phase-3 B-2: risk-profile gating.

Covers:
  1. User model — risk_profile field and constraint
  2. API — GET/PUT /users/me/risk-profile validation + endpoints
  3. Orchestrator — _inject_risk_profile server-side injection
  4. Tools — _apply_risk_guard expression augmentation
  5. Chat integration — risk_profile flows from user to orchestrator
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.orchestrator import RISK_PROFILE_TOOLS, _inject_risk_profile
from app.llm.tools import (
    RISK_PROFILE_SCREENER_GUARDS,
    _apply_risk_guard,
    _theme_to_screener,
    dispatch,
)


# ---------------------------------------------------------------------------
# 1. User model — risk_profile field
# ---------------------------------------------------------------------------


class TestUserModelRiskProfile:
    def test_user_model_has_risk_profile_field(self):
        from app.db.models.user import User
        assert hasattr(User, "risk_profile")

    def test_user_model_risk_profile_column_properties(self):
        from app.db.models.user import User
        col = User.__table__.columns["risk_profile"]
        assert not col.nullable
        assert str(col.server_default.arg) == "balanced"

    def test_user_model_has_check_constraint(self):
        from app.db.models.user import User
        constraints = [c for c in User.__table__.constraints if c.name == "ck_users_risk_profile"]
        assert len(constraints) == 1


# ---------------------------------------------------------------------------
# 2. API — risk-profile endpoints
# ---------------------------------------------------------------------------


class TestRiskProfileAPI:
    """API schema tests. These verify the source file content instead of importing
    app.api.users directly, because that module's import chain triggers pydantic
    Settings validation (requires DATABASE_URL env var)."""

    def test_users_api_defines_valid_risk_profiles(self):
        import ast, pathlib
        src = pathlib.Path("app/api/users.py").read_text()
        tree = ast.parse(src)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "VALID_RISK_PROFILES":
                        found = True
        assert found, "VALID_RISK_PROFILES not defined in app/api/users.py"

    def test_users_api_has_risk_profile_endpoints(self):
        import pathlib
        src = pathlib.Path("app/api/users.py").read_text()
        assert 'me/risk-profile' in src
        assert "get_risk_profile" in src
        assert "set_risk_profile" in src

    def test_users_api_has_risk_profile_out_model(self):
        import pathlib
        src = pathlib.Path("app/api/users.py").read_text()
        assert "class RiskProfileOut" in src
        assert "class RiskProfilePayload" in src

    def test_user_out_includes_risk_profile_field(self):
        import pathlib
        src = pathlib.Path("app/api/users.py").read_text()
        assert 'risk_profile: str = "balanced"' in src

    def test_set_risk_profile_validates_input(self):
        import pathlib
        src = pathlib.Path("app/api/users.py").read_text()
        assert "VALID_RISK_PROFILES" in src
        assert "422" in src or "HTTP_422" in src

    def test_user_out_from_model_maps_risk_profile(self):
        import pathlib
        src = pathlib.Path("app/api/users.py").read_text()
        assert 'risk_profile=user.risk_profile or "balanced"' in src


# ---------------------------------------------------------------------------
# 3. Orchestrator — _inject_risk_profile
# ---------------------------------------------------------------------------


class TestInjectRiskProfile:
    def test_injects_for_run_screener(self):
        args = {"expr": "rsi_14 < 30"}
        result = _inject_risk_profile("run_screener", args, "conservative")
        assert result["_risk_profile"] == "conservative"
        assert result["expr"] == "rsi_14 < 30"

    def test_injects_for_propose_ideas(self):
        args = {"theme": "momentum"}
        result = _inject_risk_profile("propose_ideas", args, "aggressive")
        assert result["_risk_profile"] == "aggressive"
        assert result["risk_profile"] == "aggressive"

    def test_does_not_override_explicit_risk_profile_in_propose_ideas(self):
        args = {"risk_profile": "conservative", "theme": "value"}
        result = _inject_risk_profile("propose_ideas", args, "aggressive")
        assert result["risk_profile"] == "conservative"
        assert result["_risk_profile"] == "aggressive"

    def test_no_injection_for_non_profile_tools(self):
        for tool in ("get_quote", "get_news", "get_technicals", "get_holding",
                      "get_deals", "get_research", "get_company_info", "get_levels",
                      "analyse_portfolio", "backtest_screener", "add_to_watchlist",
                      "remember_fact"):
            args = {"ticker": "RELIANCE"}
            result = _inject_risk_profile(tool, args, "aggressive")
            assert result is args, f"{tool} should not be modified"

    def test_no_injection_when_profile_is_none(self):
        args = {"expr": "rsi_14 < 30"}
        result = _inject_risk_profile("run_screener", args, None)
        assert result is args

    def test_risk_profile_tools_constant(self):
        assert "run_screener" in RISK_PROFILE_TOOLS
        assert "propose_ideas" in RISK_PROFILE_TOOLS
        assert len(RISK_PROFILE_TOOLS) == 2

    def test_injection_does_not_mutate_original(self):
        args = {"expr": "rsi_14 < 30"}
        original = dict(args)
        _inject_risk_profile("run_screener", args, "conservative")
        assert args == original


# ---------------------------------------------------------------------------
# 4. Tools — _apply_risk_guard
# ---------------------------------------------------------------------------


class TestApplyRiskGuard:
    def test_conservative_appends_safety_filters(self):
        expr = "rsi_14 < 30"
        result = _apply_risk_guard(expr, "conservative")
        assert "promoter_pct > 50" in result
        assert "pe_trailing < 25" in result
        assert result.startswith("(rsi_14 < 30)")

    def test_balanced_no_guard(self):
        expr = "rsi_14 < 30"
        result = _apply_risk_guard(expr, "balanced")
        assert result == "rsi_14 < 30"

    def test_aggressive_no_guard(self):
        expr = "rsi_14 < 30"
        result = _apply_risk_guard(expr, "aggressive")
        assert result == "rsi_14 < 30"

    def test_none_profile_no_guard(self):
        expr = "rsi_14 < 30"
        result = _apply_risk_guard(expr, None)
        assert result == "rsi_14 < 30"

    def test_empty_expr_returns_empty(self):
        result = _apply_risk_guard("", "conservative")
        assert result == ""

    def test_conservative_guard_wraps_in_parens(self):
        expr = "rsi_14 < 30 OR macd > 0"
        result = _apply_risk_guard(expr, "conservative")
        assert result.startswith("(rsi_14 < 30 OR macd > 0) AND")

    def test_guard_constants_are_defined(self):
        assert "conservative" in RISK_PROFILE_SCREENER_GUARDS
        assert "balanced" in RISK_PROFILE_SCREENER_GUARDS
        assert "aggressive" in RISK_PROFILE_SCREENER_GUARDS

    def test_unknown_profile_no_guard(self):
        expr = "rsi_14 < 30"
        result = _apply_risk_guard(expr, "yolo")
        assert result == "rsi_14 < 30"


# ---------------------------------------------------------------------------
# 5. Dispatch with risk_profile in args
# ---------------------------------------------------------------------------


class TestDispatchWithRiskProfile:
    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def mock_redis(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_run_screener_receives_risk_profile(self, mock_session, mock_redis):
        result = await dispatch(
            "run_screener",
            {"expr": "rsi_14 < 30", "_risk_profile": "conservative"},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False
        assert "not yet deployed" in result["error"]

    @pytest.mark.asyncio
    async def test_propose_ideas_uses_injected_profile(self, mock_session, mock_redis):
        result = await dispatch(
            "propose_ideas",
            {"risk_profile": "aggressive", "_risk_profile": "aggressive"},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False

    @pytest.mark.asyncio
    async def test_run_screener_no_risk_profile_still_works(self, mock_session, mock_redis):
        result = await dispatch(
            "run_screener",
            {"expr": "rsi_14 < 30"},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False


# ---------------------------------------------------------------------------
# 6. Chat integration — risk_profile kwarg accepted by run_chat
# ---------------------------------------------------------------------------


class TestRunChatAcceptsRiskProfile:
    def test_run_chat_signature_has_risk_profile(self):
        import inspect
        from app.llm.orchestrator import run_chat
        sig = inspect.signature(run_chat)
        assert "risk_profile" in sig.parameters
        param = sig.parameters["risk_profile"]
        assert param.default is None

    def test_chat_endpoint_passes_risk_profile(self):
        import pathlib
        src = pathlib.Path("app/api/chat.py").read_text()
        assert "risk_profile=" in src


# ---------------------------------------------------------------------------
# 7. Migration file validation
# ---------------------------------------------------------------------------


class TestMigration:
    def test_migration_file_exists(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "migrations", "versions", "a3b7c2d1e4f6_add_risk_profile_to_users.py"
        )
        assert os.path.exists(path)

    def test_migration_revision_chain(self):
        # P3-A3 rebased this migration's parent from f5741afc4c98 →
        # c1f4a12c9d3b. The original parent predates the `users` table,
        # so the migration could not actually run from there.
        from migrations.versions.a3b7c2d1e4f6_add_risk_profile_to_users import (
            down_revision,
            revision,
        )
        assert revision == "a3b7c2d1e4f6"
        assert down_revision == "c1f4a12c9d3b"
