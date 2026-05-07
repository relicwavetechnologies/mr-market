"""Unit tests for the per-intent tool shortlist (D8 + Phase-3 B-1 extension).

The shortlist narrows the OpenAI tool catalog *before* the workhorse runs,
so the LLM cannot pick a tool that's irrelevant to the routed intent.
"""

from __future__ import annotations

from app.llm.tool_routing import (
    ALL_TOOLS,
    SHORTLISTS,
    filter_tool_specs,
    shortlist_for,
)


# ---------------------------------------------------------------------------
# Sanity: the shortlists only reference tools that actually exist.
# ---------------------------------------------------------------------------


def test_every_shortlist_uses_known_tools():
    known = set(ALL_TOOLS)
    for intent, allowed in SHORTLISTS.items():
        for name in allowed:
            assert name in known, f"shortlist[{intent}] references unknown tool {name!r}"


def test_all_tools_matches_real_tool_catalog():
    """Cross-check ALL_TOOLS against the actual TOOL_SPECS in app.llm.tools.
    If someone adds a tool but forgets the routing module, this fails fast."""
    from app.llm.tools import TOOL_SPECS

    real = {spec["function"]["name"] for spec in TOOL_SPECS}
    declared = set(ALL_TOOLS)
    assert real == declared, (
        f"ALL_TOOLS drifted from TOOL_SPECS — "
        f"missing in ALL_TOOLS: {real - declared}, "
        f"extra in ALL_TOOLS: {declared - real}"
    )


# ---------------------------------------------------------------------------
# shortlist_for — Phase-1/2 intents
# ---------------------------------------------------------------------------


class TestShortlistFor:
    def test_quote_intent_only_quote(self):
        assert shortlist_for("quote") == ("get_quote",)

    def test_news_intent_includes_quote_fallback(self):
        out = shortlist_for("news")
        assert out is not None
        assert "get_news" in out
        assert "get_quote" in out

    def test_research_intent_only_research(self):
        assert shortlist_for("research") == ("get_research",)

    def test_holding_does_not_include_quote(self):
        out = shortlist_for("holding")
        assert out is not None
        assert "get_quote" not in out
        assert "get_holding" in out

    def test_advisory_returns_none_meaning_full_catalog(self):
        assert shortlist_for("advisory") is None

    def test_education_returns_none(self):
        assert shortlist_for("education") is None

    def test_other_returns_none(self):
        assert shortlist_for("other") is None

    def test_unknown_intent_returns_none(self):
        assert shortlist_for("nonsense_label") is None

    def test_empty_intent_returns_none(self):
        assert shortlist_for("") is None
        assert shortlist_for(None) is None


# ---------------------------------------------------------------------------
# shortlist_for — Phase-3 intents (B-1)
# ---------------------------------------------------------------------------


class TestShortlistForPhase3:
    def test_screener_intent_only_run_screener(self):
        assert shortlist_for("screener") == ("run_screener",)

    def test_portfolio_intent_only_analyse_portfolio(self):
        assert shortlist_for("portfolio") == ("analyse_portfolio",)

    def test_idea_intent_includes_screener_and_technicals(self):
        out = shortlist_for("idea")
        assert out is not None
        assert "propose_ideas" in out
        assert "run_screener" in out
        assert "get_technicals" in out

    def test_backtest_intent_only_backtest_screener(self):
        assert shortlist_for("backtest") == ("backtest_screener",)


# ---------------------------------------------------------------------------
# filter_tool_specs
# ---------------------------------------------------------------------------


def _spec(name: str) -> dict:
    """Minimal tool-spec stub matching OpenAI's shape."""
    return {"type": "function", "function": {"name": name, "description": "", "parameters": {}}}


class TestFilterToolSpecs:
    def setup_method(self):
        self.full = [_spec(n) for n in ALL_TOOLS]

    def test_quote_intent_keeps_only_quote(self):
        out = filter_tool_specs(self.full, intent="quote")
        names = [s["function"]["name"] for s in out]
        assert names == ["get_quote"]

    def test_news_intent_keeps_news_and_quote(self):
        out = filter_tool_specs(self.full, intent="news")
        names = {s["function"]["name"] for s in out}
        assert names == {"get_news", "get_quote"}

    def test_holding_intent_keeps_holding_and_deals(self):
        out = filter_tool_specs(self.full, intent="holding")
        names = {s["function"]["name"] for s in out}
        assert names == {"get_holding", "get_deals"}

    def test_research_intent_keeps_only_research(self):
        out = filter_tool_specs(self.full, intent="research")
        names = [s["function"]["name"] for s in out]
        assert names == ["get_research"]

    def test_advisory_intent_returns_full_catalog(self):
        out = filter_tool_specs(self.full, intent="advisory")
        assert out is self.full
        assert len(out) == len(ALL_TOOLS)

    def test_unknown_intent_returns_full_catalog(self):
        out = filter_tool_specs(self.full, intent="weather")
        assert len(out) == len(ALL_TOOLS)

    def test_none_intent_returns_full_catalog(self):
        out = filter_tool_specs(self.full, intent=None)
        assert len(out) == len(ALL_TOOLS)

    def test_filter_drops_unknown_specs_silently(self):
        with_extra = self.full + [_spec("get_zodiac_sign")]
        out = filter_tool_specs(with_extra, intent="quote")
        names = [s["function"]["name"] for s in out]
        assert names == ["get_quote"]
        assert "get_zodiac_sign" not in names

    def test_filter_is_pure(self):
        """The filter should not mutate the input list."""
        before = len(self.full)
        filter_tool_specs(self.full, intent="quote")
        assert len(self.full) == before

    # Phase-3 filter tests
    def test_screener_intent_keeps_only_run_screener(self):
        out = filter_tool_specs(self.full, intent="screener")
        names = [s["function"]["name"] for s in out]
        assert names == ["run_screener"]

    def test_portfolio_intent_keeps_only_analyse_portfolio(self):
        out = filter_tool_specs(self.full, intent="portfolio")
        names = [s["function"]["name"] for s in out]
        assert names == ["analyse_portfolio"]

    def test_idea_intent_keeps_propose_ideas_screener_technicals(self):
        out = filter_tool_specs(self.full, intent="idea")
        names = {s["function"]["name"] for s in out}
        assert names == {"propose_ideas", "run_screener", "get_technicals"}

    def test_backtest_intent_keeps_only_backtest_screener(self):
        out = filter_tool_specs(self.full, intent="backtest")
        names = [s["function"]["name"] for s in out]
        assert names == ["backtest_screener"]
