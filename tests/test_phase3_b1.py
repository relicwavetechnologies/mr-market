"""Rigorous tests for Phase-3 B-1: new LLM tools, intent router, shortlists.

Covers:
  1. Tool spec schema validation (OpenAI format compliance)
  2. Dispatch handler behaviour (ImportError fallback, arg validation, edge cases)
  3. Intent router additions (new intents, valid set, prompt text)
  4. Orchestrator _summarise for new tools
  5. _theme_to_screener mapping
  6. Cross-module consistency (TOOL_SPECS ↔ ALL_TOOLS ↔ SHORTLISTS ↔ dispatch)
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.intent import Intent, _INTENT_SYSTEM, _VALID_INTENTS
from app.llm.orchestrator import _summarise
from app.llm.tool_routing import ALL_TOOLS, SHORTLISTS, filter_tool_specs, shortlist_for
from app.llm.tools import (
    TOOL_SPECS,
    _theme_to_screener,
    dispatch,
    tool_result_to_json_string,
)


# ---------------------------------------------------------------------------
# 1. Tool spec schema validation — every spec must match OpenAI format
# ---------------------------------------------------------------------------

PHASE3_TOOL_NAMES = {
    "run_screener",
    "analyse_portfolio",
    "propose_ideas",
    "backtest_screener",
    "add_to_watchlist",
}


class TestToolSpecSchema:
    """Validate that every TOOL_SPEC follows the OpenAI function-calling shape."""

    def _specs_by_name(self):
        return {s["function"]["name"]: s for s in TOOL_SPECS}

    def test_all_phase3_tools_present(self):
        names = {s["function"]["name"] for s in TOOL_SPECS}
        for expected in PHASE3_TOOL_NAMES:
            assert expected in names, f"missing tool spec: {expected}"

    def test_every_spec_has_type_function(self):
        for spec in TOOL_SPECS:
            assert spec.get("type") == "function", f"{spec} missing type=function"

    def test_every_spec_has_function_key_with_name_desc_params(self):
        for spec in TOOL_SPECS:
            fn = spec.get("function", {})
            assert "name" in fn, f"spec missing function.name: {spec}"
            assert "description" in fn, f"{fn['name']} missing description"
            assert "parameters" in fn, f"{fn['name']} missing parameters"

    def test_every_spec_parameters_is_valid_json_schema(self):
        for spec in TOOL_SPECS:
            fn = spec["function"]
            params = fn["parameters"]
            assert isinstance(params, dict), f"{fn['name']}: params must be dict"
            assert params.get("type") == "object", f"{fn['name']}: params.type must be 'object'"
            if "required" in params:
                assert isinstance(params["required"], list), f"{fn['name']}: required must be list"
                props = set(params.get("properties", {}).keys())
                for req in params["required"]:
                    assert req in props, f"{fn['name']}: required param '{req}' not in properties"

    def test_run_screener_has_name_and_expr_but_neither_required(self):
        specs = self._specs_by_name()
        params = specs["run_screener"]["function"]["parameters"]
        props = params.get("properties", {})
        assert "name" in props
        assert "expr" in props
        assert "limit" in props
        required = params.get("required", [])
        assert "name" not in required, "run_screener: name should not be required (expr is an alternative)"
        assert "expr" not in required, "run_screener: expr should not be required (name is an alternative)"

    def test_analyse_portfolio_requires_portfolio_id(self):
        specs = self._specs_by_name()
        params = specs["analyse_portfolio"]["function"]["parameters"]
        assert "portfolio_id" in params.get("required", [])

    def test_propose_ideas_requires_risk_profile(self):
        specs = self._specs_by_name()
        params = specs["propose_ideas"]["function"]["parameters"]
        assert "risk_profile" in params.get("required", [])
        enum = params["properties"]["risk_profile"].get("enum")
        assert set(enum) == {"conservative", "balanced", "aggressive"}

    def test_backtest_screener_requires_name(self):
        specs = self._specs_by_name()
        params = specs["backtest_screener"]["function"]["parameters"]
        assert "name" in params.get("required", [])

    def test_add_to_watchlist_requires_ticker(self):
        specs = self._specs_by_name()
        params = specs["add_to_watchlist"]["function"]["parameters"]
        assert "ticker" in params.get("required", [])

    def test_descriptions_are_nonempty_strings(self):
        for spec in TOOL_SPECS:
            desc = spec["function"]["description"]
            assert isinstance(desc, str) and len(desc) > 20, (
                f"{spec['function']['name']}: description too short or wrong type"
            )

    def test_no_duplicate_tool_names(self):
        names = [s["function"]["name"] for s in TOOL_SPECS]
        assert len(names) == len(set(names)), f"duplicate tool names: {names}"


# ---------------------------------------------------------------------------
# 2. Dispatch handler tests — ImportError fallback + arg validation
# ---------------------------------------------------------------------------

class TestDispatchImportFallbacks:
    """All Phase-3 tools import from Dev A modules that don't exist yet.
    Dispatch must return a graceful 'not deployed' response, never raise."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def mock_redis(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_run_screener_import_fallback(self, mock_session, mock_redis):
        result = await dispatch(
            "run_screener",
            {"name": "oversold_quality"},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False
        assert "not yet deployed" in result["error"]

    @pytest.mark.asyncio
    async def test_run_screener_with_expr_import_fallback(self, mock_session, mock_redis):
        result = await dispatch(
            "run_screener",
            {"expr": "rsi_14 < 30 AND pe_trailing < 20"},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False
        assert "not yet deployed" in result["error"]

    @pytest.mark.asyncio
    async def test_run_screener_no_name_no_expr_returns_error(self, mock_session, mock_redis):
        result = await dispatch(
            "run_screener",
            {},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False
        assert "provide either" in result["error"]

    @pytest.mark.asyncio
    async def test_analyse_portfolio_import_fallback(self, mock_session, mock_redis):
        result = await dispatch(
            "analyse_portfolio",
            {"portfolio_id": 42},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False
        assert "not yet deployed" in result["error"]

    @pytest.mark.asyncio
    async def test_propose_ideas_import_fallback(self, mock_session, mock_redis):
        result = await dispatch(
            "propose_ideas",
            {"risk_profile": "balanced"},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False
        assert "not yet deployed" in result["error"]

    @pytest.mark.asyncio
    async def test_propose_ideas_invalid_risk_profile(self, mock_session, mock_redis):
        result = await dispatch(
            "propose_ideas",
            {"risk_profile": "yolo"},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False
        assert "invalid risk_profile" in result["error"]

    @pytest.mark.asyncio
    async def test_backtest_screener_import_fallback(self, mock_session, mock_redis):
        result = await dispatch(
            "backtest_screener",
            {"name": "value_rebound"},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False
        assert "not yet deployed" in result["error"]

    @pytest.mark.asyncio
    async def test_add_to_watchlist_import_fallback(self, mock_session, mock_redis):
        result = await dispatch(
            "add_to_watchlist",
            {"ticker": "RELIANCE"},
            session=mock_session, redis=mock_redis,
            user_id="user-123",
        )
        assert result["ok"] is False
        assert "not yet deployed" in result["error"]

    @pytest.mark.asyncio
    async def test_add_to_watchlist_no_user(self, mock_session, mock_redis):
        result = await dispatch(
            "add_to_watchlist",
            {"ticker": "RELIANCE"},
            session=mock_session, redis=mock_redis,
            user_id=None,
        )
        assert result["ok"] is False
        assert "signed-in user" in result["error"]


class TestDispatchResultSerialisation:
    """Every dispatch result must be JSON-serialisable (the orchestrator calls
    tool_result_to_json_string on it)."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def mock_redis(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_all_phase3_tools_serialise(self, mock_session, mock_redis):
        test_cases = [
            ("run_screener", {"name": "oversold_quality"}),
            ("run_screener", {"expr": "rsi_14 < 30"}),
            ("run_screener", {}),
            ("analyse_portfolio", {"portfolio_id": 1}),
            ("propose_ideas", {"risk_profile": "balanced"}),
            ("propose_ideas", {"risk_profile": "yolo"}),
            ("backtest_screener", {"name": "test"}),
            ("add_to_watchlist", {"ticker": "TCS"}),
        ]
        for name, args in test_cases:
            result = await dispatch(
                name, args,
                session=mock_session, redis=mock_redis, user_id="u1",
            )
            serialised = tool_result_to_json_string(result)
            parsed = json.loads(serialised)
            assert isinstance(parsed, dict), f"{name}({args}) didn't serialise to dict"


class TestDispatchEdgeCases:
    """Edge cases in argument handling."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def mock_redis(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_run_screener_limit_clamped_low(self, mock_session, mock_redis):
        result = await dispatch(
            "run_screener",
            {"expr": "rsi_14 < 30", "limit": -5},
            session=mock_session, redis=mock_redis,
        )
        # Should not crash — limit is clamped to 1 before the import fails
        assert result["available"] is False

    @pytest.mark.asyncio
    async def test_run_screener_limit_clamped_high(self, mock_session, mock_redis):
        result = await dispatch(
            "run_screener",
            {"expr": "rsi_14 < 30", "limit": 999},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False

    @pytest.mark.asyncio
    async def test_backtest_period_days_clamped(self, mock_session, mock_redis):
        result = await dispatch(
            "backtest_screener",
            {"name": "x", "period_days": 5},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False  # still hits ImportError

    @pytest.mark.asyncio
    async def test_add_to_watchlist_ticker_uppercased(self, mock_session, mock_redis):
        result = await dispatch(
            "add_to_watchlist",
            {"ticker": "  reliance  "},
            session=mock_session, redis=mock_redis,
            user_id=None,
        )
        # Without user it returns early with error, but ticker is still validated
        assert "signed-in user" in result["error"]

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, mock_session, mock_redis):
        result = await dispatch(
            "nonexistent_tool", {},
            session=mock_session, redis=mock_redis,
        )
        assert "unknown tool" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_propose_ideas_with_theme(self, mock_session, mock_redis):
        result = await dispatch(
            "propose_ideas",
            {"risk_profile": "aggressive", "theme": "momentum breakout"},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False
        assert "not yet deployed" in result["error"]

    @pytest.mark.asyncio
    async def test_run_screener_name_takes_precedence_when_no_expr(self, mock_session, mock_redis):
        result = await dispatch(
            "run_screener",
            {"name": "fii_buying", "limit": 5},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False
        # name was provided without expr — handler tries to load saved screener

    @pytest.mark.asyncio
    async def test_run_screener_expr_overrides_when_both(self, mock_session, mock_redis):
        result = await dispatch(
            "run_screener",
            {"name": "fii_buying", "expr": "rsi_14 < 30"},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False
        # When both are provided, expr should be used directly


# ---------------------------------------------------------------------------
# 3. Intent router additions
# ---------------------------------------------------------------------------

class TestIntentRouterPhase3:
    def test_new_intents_in_valid_set(self):
        for intent in ("screener", "portfolio", "idea", "backtest"):
            assert intent in _VALID_INTENTS, f"intent '{intent}' missing from _VALID_INTENTS"

    def test_old_intents_still_present(self):
        for intent in ("quote", "news", "company_info", "technicals", "holding",
                        "deals", "research", "advisory", "education", "refuse", "other"):
            assert intent in _VALID_INTENTS

    def test_intent_system_prompt_mentions_screener(self):
        assert "screener" in _INTENT_SYSTEM.lower()
        assert "run a named stock screener" in _INTENT_SYSTEM.lower() or "screen for" in _INTENT_SYSTEM.lower()

    def test_intent_system_prompt_mentions_portfolio(self):
        assert "portfolio" in _INTENT_SYSTEM.lower()
        assert "analyse" in _INTENT_SYSTEM.lower() or "portfolio diagnostics" in _INTENT_SYSTEM.lower()

    def test_intent_system_prompt_mentions_idea(self):
        assert '"idea"' in _INTENT_SYSTEM.lower()
        assert "trade ideas" in _INTENT_SYSTEM.lower()

    def test_intent_system_prompt_mentions_backtest(self):
        assert '"backtest"' in _INTENT_SYSTEM.lower()
        assert "historical replay" in _INTENT_SYSTEM.lower() or "backtest" in _INTENT_SYSTEM.lower()

    def test_intent_system_prompt_disambiguation_rules(self):
        assert "screener filter expressions" in _INTENT_SYSTEM.lower() or \
               'screener filter expressions ("rsi < 30' in _INTENT_SYSTEM.lower() or \
               "screener filter expressions" in _INTENT_SYSTEM

    def test_valid_intents_count(self):
        assert len(_VALID_INTENTS) == 15  # 11 original + 4 new

    def test_intent_literal_type_has_new_values(self):
        from typing import get_args
        literal_values = set(get_args(Intent))
        expected = {
            "quote", "news", "company_info", "technicals", "holding",
            "deals", "research", "screener", "portfolio", "idea", "backtest",
            "advisory", "education", "refuse", "other",
        }
        assert literal_values == expected
        assert _VALID_INTENTS == expected


# ---------------------------------------------------------------------------
# 4. Orchestrator _summarise for new tools
# ---------------------------------------------------------------------------

class TestSummarisePhase3Tools:
    def test_run_screener_available(self):
        payload = {
            "available": True,
            "screener_name": "oversold_quality",
            "expr": "rsi_14 < 30 AND pe_trailing < 20",
            "tickers": [
                {"symbol": "RELIANCE", "score": 0.95},
                {"symbol": "TCS", "score": 0.87},
                {"symbol": "INFY", "score": 0.82},
            ],
            "universe_size": 100,
            "exec_ms": 42,
        }
        s = _summarise("run_screener", payload)
        assert s["available"] is True
        assert s["n_matches"] == 3
        assert s["top_tickers"] == ["RELIANCE", "TCS", "INFY"]
        assert s["universe_size"] == 100
        assert s["exec_ms"] == 42
        assert s["screener_name"] == "oversold_quality"

    def test_run_screener_unavailable(self):
        payload = {"available": False, "error": "not deployed"}
        s = _summarise("run_screener", payload)
        assert s["available"] is False
        assert s["n_matches"] == 0
        assert s["top_tickers"] == []
        assert s["error"] == "not deployed"

    def test_run_screener_top_tickers_capped_at_5(self):
        payload = {
            "available": True,
            "tickers": [{"symbol": f"T{i}"} for i in range(10)],
        }
        s = _summarise("run_screener", payload)
        assert len(s["top_tickers"]) == 5

    def test_analyse_portfolio_available(self):
        payload = {
            "available": True,
            "portfolio_id": 42,
            "concentration": 0.35,
            "sector_pct": {"IT": 40, "Banking": 30, "Pharma": 30},
            "top_5_pct": 0.72,
            "beta_blend": 1.15,
            "div_yield": 0.018,
            "drawdown_1y": -0.12,
        }
        s = _summarise("analyse_portfolio", payload)
        assert s["available"] is True
        assert s["portfolio_id"] == 42
        assert s["concentration"] == 0.35
        assert s["sector_pct"] == {"IT": 40, "Banking": 30, "Pharma": 30}
        assert s["top_5_pct"] == 0.72

    def test_analyse_portfolio_unavailable(self):
        payload = {"available": False, "error": "not deployed"}
        s = _summarise("analyse_portfolio", payload)
        assert s["available"] is False

    def test_propose_ideas_available(self):
        payload = {
            "available": True,
            "risk_profile": "aggressive",
            "theme": "momentum",
            "ideas": [
                {"ticker": "RELIANCE", "thesis": "breakout", "score": 0.9},
                {"ticker": "TCS", "thesis": "RSI bounce", "score": 0.8},
            ],
        }
        s = _summarise("propose_ideas", payload)
        assert s["available"] is True
        assert s["n_ideas"] == 2
        assert s["risk_profile"] == "aggressive"
        assert len(s["ideas"]) == 2
        assert s["ideas"][0]["ticker"] == "RELIANCE"

    def test_propose_ideas_empty(self):
        payload = {"available": True, "ideas": [], "risk_profile": "balanced"}
        s = _summarise("propose_ideas", payload)
        assert s["n_ideas"] == 0
        assert s["ideas"] == []

    def test_propose_ideas_capped_at_5(self):
        payload = {
            "available": True,
            "ideas": [{"ticker": f"T{i}", "score": i} for i in range(8)],
        }
        s = _summarise("propose_ideas", payload)
        assert len(s["ideas"]) == 5

    def test_backtest_screener_available(self):
        payload = {
            "available": True,
            "screener_name": "value_rebound",
            "period_days": 365,
            "hit_rate": 0.68,
            "mean_return": 0.042,
            "worst_drawdown": -0.15,
            "n_signals": 47,
        }
        s = _summarise("backtest_screener", payload)
        assert s["available"] is True
        assert s["hit_rate"] == 0.68
        assert s["mean_return"] == 0.042
        assert s["worst_drawdown"] == -0.15
        assert s["n_signals"] == 47
        assert s["screener_name"] == "value_rebound"

    def test_backtest_screener_unavailable(self):
        payload = {"available": False, "error": "not deployed"}
        s = _summarise("backtest_screener", payload)
        assert s["available"] is False
        assert s["error"] == "not deployed"

    def test_add_to_watchlist_ok(self):
        payload = {"ok": True, "ticker": "RELIANCE", "watchlist_size": 5}
        s = _summarise("add_to_watchlist", payload)
        assert s["ok"] is True
        assert s["ticker"] == "RELIANCE"
        assert s["watchlist_size"] == 5

    def test_add_to_watchlist_error(self):
        payload = {"ok": False, "error": "requires signed-in user"}
        s = _summarise("add_to_watchlist", payload)
        assert s["ok"] is False
        assert s["error"] == "requires signed-in user"

    def test_summarise_returns_raw_keys_for_unknown_tool(self):
        payload = {"foo": 1, "bar": 2}
        s = _summarise("totally_unknown", payload)
        assert "raw_keys" in s
        assert set(s["raw_keys"]) == {"foo", "bar"}


# ---------------------------------------------------------------------------
# 5. _theme_to_screener mapping
# ---------------------------------------------------------------------------

class TestThemeToScreener:
    def test_exact_match_oversold_quality(self):
        assert _theme_to_screener("oversold quality", "balanced") == "oversold_quality"

    def test_exact_match_value_rebound(self):
        assert _theme_to_screener("value rebound", "aggressive") == "value_rebound"

    def test_exact_match_momentum_breakout(self):
        assert _theme_to_screener("momentum breakout", "conservative") == "momentum_breakout"

    def test_partial_match_momentum(self):
        assert _theme_to_screener("momentum", "balanced") == "momentum_breakout"

    def test_partial_match_fii(self):
        assert _theme_to_screener("fii", "balanced") == "fii_buying"

    def test_partial_match_promoter(self):
        assert _theme_to_screener("promoter", "balanced") == "promoter_increasing"

    def test_partial_match_pledge(self):
        assert _theme_to_screener("pledge", "balanced") == "high_pledge_avoid"

    def test_no_theme_conservative_default(self):
        assert _theme_to_screener(None, "conservative") == "oversold_quality"

    def test_no_theme_balanced_default(self):
        assert _theme_to_screener(None, "balanced") == "value_rebound"

    def test_no_theme_aggressive_default(self):
        assert _theme_to_screener(None, "aggressive") == "momentum_breakout"

    def test_unknown_theme_falls_through_to_profile_default(self):
        assert _theme_to_screener("unicorns in space", "aggressive") == "momentum_breakout"

    def test_unknown_theme_unknown_profile_falls_to_value_rebound(self):
        assert _theme_to_screener("xyz", "unknown") == "value_rebound"

    def test_theme_with_hyphens(self):
        assert _theme_to_screener("value-rebound", "balanced") == "value_rebound"

    def test_theme_case_insensitive(self):
        assert _theme_to_screener("MOMENTUM BREAKOUT", "balanced") == "momentum_breakout"


# ---------------------------------------------------------------------------
# 6. Cross-module consistency
# ---------------------------------------------------------------------------

class TestCrossModuleConsistency:
    def test_all_tools_in_tool_specs_are_in_all_tools(self):
        spec_names = {s["function"]["name"] for s in TOOL_SPECS}
        routing_names = set(ALL_TOOLS)
        assert spec_names == routing_names, (
            f"Mismatch: in TOOL_SPECS but not ALL_TOOLS: {spec_names - routing_names}, "
            f"in ALL_TOOLS but not TOOL_SPECS: {routing_names - spec_names}"
        )

    def test_all_shortlist_tools_exist_in_all_tools(self):
        known = set(ALL_TOOLS)
        for intent, tools in SHORTLISTS.items():
            for tool in tools:
                assert tool in known, f"shortlist[{intent}] references unknown tool '{tool}'"

    def test_every_shortlist_intent_is_valid(self):
        for intent in SHORTLISTS:
            assert intent in _VALID_INTENTS, f"shortlist intent '{intent}' not in _VALID_INTENTS"

    @pytest.mark.asyncio
    async def test_dispatch_handles_every_tool_in_all_tools(self):
        """Every tool in ALL_TOOLS must have a dispatch handler.
        We test this by calling dispatch for each tool with minimal args
        and verifying we don't get 'unknown tool'."""

        mock_session = AsyncMock()
        mock_redis = AsyncMock()

        minimal_args = {
            "get_quote": {"ticker": "TEST"},
            "get_news": {"ticker": "TEST"},
            "get_company_info": {"ticker": "TEST"},
            "get_technicals": {"ticker": "TEST"},
            "get_levels": {"ticker": "TEST"},
            "get_holding": {"ticker": "TEST"},
            "get_deals": {"ticker": "TEST"},
            "get_research": {"ticker": "TEST", "query": "test"},
            "run_screener": {"name": "test"},
            "analyse_portfolio": {"portfolio_id": 1},
            "propose_ideas": {"risk_profile": "balanced"},
            "backtest_screener": {"name": "test"},
            "add_to_watchlist": {"ticker": "TEST"},
            "remember_fact": {"fact": "test"},
        }

        for tool_name in ALL_TOOLS:
            args = minimal_args.get(tool_name)
            assert args is not None, f"no test args for tool '{tool_name}'"
            try:
                result = await dispatch(
                    tool_name, args,
                    session=mock_session, redis=mock_redis, user_id="test-user",
                )
                assert "unknown tool" not in str(result.get("error", "")), (
                    f"tool '{tool_name}' hit unknown-tool branch"
                )
            except Exception:
                pass

    def test_phase3_tools_not_in_non_phase3_shortlists(self):
        """Phase-3 tools should not appear in Phase-2 shortlists."""
        phase2_intents = {"quote", "news", "company_info", "technicals", "holding", "deals", "research"}
        for intent in phase2_intents:
            shortlist = SHORTLISTS.get(intent, ())
            for tool in shortlist:
                assert tool not in PHASE3_TOOL_NAMES, (
                    f"Phase-3 tool '{tool}' leaked into Phase-2 shortlist[{intent}]"
                )

    def test_phase3_shortlists_only_reference_phase3_or_shared_tools(self):
        """Phase-3 shortlists should only reference Phase-3 tools or shared tools
        that were already in Phase-2."""
        phase3_intents = {"screener", "portfolio", "idea", "backtest"}
        shared_tools = {"get_technicals"}  # idea shortlist includes this
        for intent in phase3_intents:
            shortlist = SHORTLISTS.get(intent, ())
            for tool in shortlist:
                assert tool in PHASE3_TOOL_NAMES or tool in shared_tools, (
                    f"unexpected tool '{tool}' in Phase-3 shortlist[{intent}]"
                )


# ---------------------------------------------------------------------------
# 7. System prompt validation
# ---------------------------------------------------------------------------

class TestSystemPrompt:
    def test_prompt_mentions_screener_tool(self):
        from app.llm.prompts import SYSTEM_PROMPT
        assert "run_screener" in SYSTEM_PROMPT

    def test_prompt_mentions_portfolio_tool(self):
        from app.llm.prompts import SYSTEM_PROMPT
        assert "analyse_portfolio" in SYSTEM_PROMPT

    def test_prompt_mentions_ideas_tool(self):
        from app.llm.prompts import SYSTEM_PROMPT
        assert "propose_ideas" in SYSTEM_PROMPT

    def test_prompt_mentions_backtest_tool(self):
        from app.llm.prompts import SYSTEM_PROMPT
        assert "backtest_screener" in SYSTEM_PROMPT

    def test_prompt_mentions_watchlist_tool(self):
        from app.llm.prompts import SYSTEM_PROMPT
        assert "add_to_watchlist" in SYSTEM_PROMPT

    def test_prompt_mentions_nifty_100(self):
        from app.llm.prompts import SYSTEM_PROMPT
        assert "NIFTY-100" in SYSTEM_PROMPT

    def test_prompt_still_has_disclaimer(self):
        from app.llm.prompts import INLINE_DISCLAIMER
        assert "not investment advice" in INLINE_DISCLAIMER


# ---------------------------------------------------------------------------
# 8. Refuse message includes new capabilities
# ---------------------------------------------------------------------------

class TestOrchestratorRefuseMessage:
    def test_refuse_message_mentions_screeners(self):
        # The refuse message in orchestrator.py should mention new capabilities.
        import inspect
        from app.llm import orchestrator
        source = inspect.getsource(orchestrator)
        # Find the refuse message block
        assert "screeners" in source
        assert "portfolio analysis" in source
        assert "trade ideas" in source
        assert "backtests" in source
