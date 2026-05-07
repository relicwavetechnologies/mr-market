"""Tests for Phase-3 B-3: trade-idea engine + numeric verifier extension.

Covers:
  1. _build_idea — idea composition from technicals + levels
  2. _propose_ideas_payload — ImportError fallback, invalid profile
  3. collect_idea_truth — verifier extracts entry/sl/target numbers
  4. Guardrail integration — idea numbers land in the truth set
  5. Regression — existing guardrail tests still pass
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.llm.guardrails import (
    collect_idea_truth,
    collect_truth_set,
    apply_guardrails,
    verify_claims,
)
from app.llm.tools import _build_idea, dispatch


# ---------------------------------------------------------------------------
# 1. _build_idea — composing an idea from technicals + levels
# ---------------------------------------------------------------------------


class TestBuildIdea:
    def _tech(self, **overrides):
        latest = {
            "close": "1500.00",
            "rsi_14": "42.5",
            "atr_14": "30.00",
            "macd": "5.0",
            "macd_signal": "3.0",
            "sma_50": "1480.00",
            "sma_200": "1400.00",
        }
        latest.update(overrides.pop("latest", {}))
        summary = {
            "available": True,
            "rsi_zone": "neutral",
            "macd_above_signal": True,
            "above_sma50": True,
            "above_sma200": True,
        }
        summary.update(overrides.pop("summary", {}))
        return {"latest": latest, "summary": summary, **overrides}

    def _levels(self, resistance=None, support=None):
        return {
            "available": True,
            "resistance": resistance or [{"level": 1550.0, "touches": 3}],
            "support": support or [{"level": 1450.0, "touches": 2}],
        }

    def test_basic_idea_structure(self):
        idea = _build_idea("RELIANCE", self._tech(), self._levels(), "balanced")
        assert idea is not None
        assert idea["ticker"] == "RELIANCE"
        assert "entry" in idea
        assert "sl" in idea
        assert "target" in idea
        assert "score" in idea
        assert "thesis" in idea
        assert "rr_ratio" in idea
        assert "technicals_snapshot" in idea

    def test_entry_equals_close(self):
        idea = _build_idea("TCS", self._tech(), self._levels(), "balanced")
        assert idea["entry"] == 1500.0

    def test_sl_uses_atr(self):
        idea = _build_idea("TCS", self._tech(), self._levels(), "balanced")
        assert idea["sl"] == 1470.0  # 1500 - 30*1.0

    def test_sl_conservative_wider(self):
        idea = _build_idea("TCS", self._tech(), self._levels(), "conservative")
        assert idea["sl"] == 1455.0  # 1500 - 30*1.5

    def test_sl_aggressive_tighter(self):
        idea = _build_idea("TCS", self._tech(), self._levels(), "aggressive")
        assert idea["sl"] == 1477.5  # 1500 - 30*0.75

    def test_target_from_resistance(self):
        idea = _build_idea("TCS", self._tech(), self._levels(
            resistance=[{"level": 1580.0, "touches": 2}]
        ), "balanced")
        assert idea["target"] == 1580.0

    def test_target_fallback_when_no_resistance(self):
        idea = _build_idea("TCS", self._tech(), self._levels(resistance=[]), "balanced")
        # Fallback: The _levels helper passes support=[{level:1450}] so
        # _build_idea still finds the first resistance from the default levels.
        # With completely empty levels, target = close + atr*2
        tech = self._tech()
        idea2 = _build_idea("TCS", tech, {"resistance": [], "support": []}, "balanced")
        assert idea2["target"] == 1560.0  # 1500 + 30*2

    def test_target_skips_resistance_below_close(self):
        idea = _build_idea("TCS", self._tech(), self._levels(
            resistance=[{"level": 1400.0, "touches": 5}, {"level": 1600.0, "touches": 2}]
        ), "balanced")
        assert idea["target"] == 1600.0

    def test_returns_none_when_no_close(self):
        tech = self._tech(latest={"close": None, "atr_14": "30"})
        idea = _build_idea("TCS", tech, self._levels(), "balanced")
        assert idea is None

    def test_score_capped_at_1(self):
        tech = self._tech(
            latest={"close": "100", "rsi_14": "25", "atr_14": "2"},
            summary={
                "rsi_zone": "oversold",
                "macd_above_signal": True,
                "above_sma50": True,
                "above_sma200": True,
            },
        )
        levels = self._levels(resistance=[{"level": 200.0, "touches": 3}])
        idea = _build_idea("TEST", tech, levels, "balanced")
        assert idea["score"] <= 1.0

    def test_thesis_contains_rsi_zone(self):
        idea = _build_idea("TCS", self._tech(), self._levels(), "balanced")
        assert "RSI" in idea["thesis"]
        assert "neutral" in idea["thesis"]

    def test_thesis_contains_rr_ratio(self):
        idea = _build_idea("TCS", self._tech(), self._levels(), "balanced")
        assert "R:R" in idea["thesis"]

    def test_thesis_macd_bullish(self):
        idea = _build_idea("TCS", self._tech(), self._levels(), "balanced")
        assert "MACD bullish" in idea["thesis"]

    def test_thesis_macd_bearish(self):
        tech = self._tech(summary={"macd_above_signal": False, "above_sma50": True, "above_sma200": True})
        idea = _build_idea("TCS", tech, self._levels(), "balanced")
        assert "MACD bearish" in idea["thesis"]

    def test_technicals_snapshot_present(self):
        idea = _build_idea("TCS", self._tech(), self._levels(), "balanced")
        snap = idea["technicals_snapshot"]
        assert snap["close"] == 1500.0
        assert snap["rsi_14"] == "42.5"
        assert snap["atr_14"] == "30.00"

    def test_atr_fallback_when_none(self):
        tech = self._tech(latest={"close": "1000", "rsi_14": "50", "atr_14": None})
        idea = _build_idea("TCS", tech, self._levels(), "balanced")
        assert idea is not None
        assert idea["sl"] == 980.0  # 1000 - (1000*0.02)*1.0


# ---------------------------------------------------------------------------
# 2. _propose_ideas_payload — dispatch tests
# ---------------------------------------------------------------------------


class TestProposeIdeasDispatch:
    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def mock_redis(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_import_fallback(self, mock_session, mock_redis):
        result = await dispatch(
            "propose_ideas",
            {"risk_profile": "balanced"},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False
        assert "not yet deployed" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_profile_rejected(self, mock_session, mock_redis):
        result = await dispatch(
            "propose_ideas",
            {"risk_profile": "reckless"},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False
        assert "invalid risk_profile" in result["error"]

    @pytest.mark.asyncio
    async def test_with_theme(self, mock_session, mock_redis):
        result = await dispatch(
            "propose_ideas",
            {"risk_profile": "aggressive", "theme": "momentum breakout"},
            session=mock_session, redis=mock_redis,
        )
        assert result["available"] is False


# ---------------------------------------------------------------------------
# 3. collect_idea_truth — verifier picks up idea numbers
# ---------------------------------------------------------------------------


class TestCollectIdeaTruth:
    def test_extracts_entry_sl_target(self):
        tool_results = {
            "propose_ideas": [
                {
                    "args": {"risk_profile": "balanced"},
                    "result": {
                        "available": True,
                        "ideas": [
                            {
                                "ticker": "RELIANCE",
                                "entry": 1500.0,
                                "sl": 1470.0,
                                "target": 1580.0,
                                "rr_ratio": 2.67,
                                "score": 0.65,
                            },
                        ],
                    },
                },
            ],
        }
        truth = collect_idea_truth(tool_results)
        assert Decimal("1500.0") in truth
        assert Decimal("1470.0") in truth
        assert Decimal("1580.0") in truth
        assert Decimal("2.67") in truth
        assert Decimal("0.65") in truth

    def test_extracts_technicals_snapshot(self):
        tool_results = {
            "propose_ideas": [
                {
                    "result": {
                        "ideas": [
                            {
                                "ticker": "TCS",
                                "entry": 100,
                                "sl": 95,
                                "target": 110,
                                "score": 0.5,
                                "technicals_snapshot": {
                                    "close": 100,
                                    "rsi_14": "42.5",
                                    "atr_14": "5.0",
                                    "rsi_zone": "neutral",
                                    "macd_above_signal": True,
                                    "above_sma50": True,
                                },
                            },
                        ],
                    },
                },
            ],
        }
        truth = collect_idea_truth(tool_results)
        assert Decimal("42.5") in truth
        assert Decimal("5.0") in truth
        assert Decimal("100") in truth
        # Booleans and strings should not crash — just verify no exception
        # (non-numeric strings like "neutral" are silently skipped)

    def test_empty_ideas(self):
        tool_results = {"propose_ideas": [{"result": {"ideas": []}}]}
        truth = collect_idea_truth(tool_results)
        assert truth == set()

    def test_no_propose_ideas(self):
        tool_results = {"get_quote": [{"result": {"price": 100}}]}
        truth = collect_idea_truth(tool_results)
        assert truth == set()

    def test_none_tool_results(self):
        truth = collect_idea_truth({})
        assert truth == set()

    def test_multiple_ideas(self):
        tool_results = {
            "propose_ideas": [
                {
                    "result": {
                        "ideas": [
                            {"ticker": "A", "entry": 100, "sl": 95, "target": 110, "score": 0.8},
                            {"ticker": "B", "entry": 200, "sl": 190, "target": 220, "score": 0.6},
                        ],
                    },
                },
            ],
        }
        truth = collect_idea_truth(tool_results)
        assert Decimal("100") in truth
        assert Decimal("200") in truth
        assert Decimal("95") in truth
        assert Decimal("190") in truth
        assert Decimal("110") in truth
        assert Decimal("220") in truth


# ---------------------------------------------------------------------------
# 4. Guardrail integration — idea numbers in the truth set
# ---------------------------------------------------------------------------


class TestGuardrailWithIdeas:
    def test_idea_numbers_pass_verifier(self):
        text = "RELIANCE entry at ₹1500, SL at ₹1470, target ₹1580."
        tool_results = {
            "propose_ideas": [
                {
                    "result": {
                        "ideas": [
                            {
                                "ticker": "RELIANCE",
                                "entry": 1500.0,
                                "sl": 1470.0,
                                "target": 1580.0,
                                "score": 0.65,
                            },
                        ],
                    },
                },
            ],
        }
        truth = collect_truth_set(tool_results) | collect_idea_truth(tool_results)
        mismatches = verify_claims(text, truth)
        assert len(mismatches) == 0

    def test_fabricated_number_caught(self):
        text = "RELIANCE entry at ₹1500, SL at ₹1470, target ₹2000."
        tool_results = {
            "propose_ideas": [
                {
                    "result": {
                        "ideas": [
                            {
                                "ticker": "RELIANCE",
                                "entry": 1500.0,
                                "sl": 1470.0,
                                "target": 1580.0,
                                "score": 0.65,
                            },
                        ],
                    },
                },
            ],
        }
        truth = collect_truth_set(tool_results) | collect_idea_truth(tool_results)
        mismatches = verify_claims(text, truth)
        fabricated = [m for m in mismatches if m.value == "2000"]
        assert len(fabricated) == 1

    def test_apply_guardrails_includes_idea_truth(self):
        text = "Entry ₹1500, target ₹1580."
        tool_results = {
            "propose_ideas": [
                {
                    "result": {
                        "ideas": [
                            {"entry": 1500.0, "target": 1580.0, "sl": 1470.0, "score": 0.5},
                        ],
                    },
                },
            ],
        }
        guarded = apply_guardrails(text, tool_results=tool_results)
        assert not guarded.claim_mismatches


# ---------------------------------------------------------------------------
# 5. Regression — existing guardrail behaviour unchanged
# ---------------------------------------------------------------------------


class TestGuardrailRegression:
    def test_blocklist_still_works(self):
        from app.llm.guardrails import find_blocklist_hits
        hits = find_blocklist_hits("you should buy Reliance immediately")
        assert len(hits) > 0
        assert any(h.category == "recommendation" for h in hits)

    def test_numeric_verifier_still_works(self):
        truth = {Decimal("1436.10"), Decimal("67.2")}
        mismatches = verify_claims("Price is ₹1436.10 with RSI 67.2", truth)
        assert len(mismatches) == 0

    def test_disclaimer_injector_still_works(self):
        from app.llm.guardrails import maybe_inject_disclaimer
        from app.analytics.ticker_ner import TickerEntry, TickerIndex
        import re
        entry = TickerEntry(ticker="RELIANCE", aliases=("reliance",))
        index = TickerIndex(entries=(entry,), pattern=re.compile(r"\breliance\b", re.IGNORECASE))
        text, injected = maybe_inject_disclaimer("Reliance looks good", index)
        assert injected
        assert "not investment advice" in text

    def test_strict_mode_still_overrides(self):
        result = apply_guardrails(
            "you should buy Reliance at ₹1500",
            mode="strict",
        )
        assert result.overridden

    def test_warn_mode_does_not_override(self):
        result = apply_guardrails(
            "you should buy Reliance at ₹1500",
            mode="warn",
        )
        assert not result.overridden
        assert len(result.blocklist_hits) > 0
