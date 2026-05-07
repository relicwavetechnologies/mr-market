"""Intent → tool shortlist.

The router classifies every user message into one of 11 coarse intents
before the workhorse runs. We use that label to *narrow* the tool catalog
the model sees on each turn — the model still picks tools autonomously
inside that narrowed set, but we stop it from grabbing 4 tools when the
question only needed 1.

Why narrow at all (instead of trusting `tool_choice="auto"`):

- Latency. Each tool round adds ~300-700ms (DB + scrape).
- Cost. Each extra tool call burns input tokens on the result it returns.
- Faithfulness. More tools = more chances to weave a number from the
  wrong source into the final answer (e.g. quoting yfinance after the
  user asked for shareholding).

Rules:

- The shortlist is **advisory only** — if the intent is `other`, `education`,
  or `advisory`, we widen back to the full catalog because the user may
  legitimately want anything.
- The intent classifier sometimes mislabels (e.g. routes "what's the news"
  to `news` when the user said "tell me about Reliance"). To keep the
  model from being trapped, we always include `get_quote` + `get_news`
  in every shortlist except the pure-RAG / refuse paths.
- A `None` return means "do not narrow, hand over the full catalog".
"""

from __future__ import annotations

from typing import Any

# Every tool name must appear in app.llm.tools.TOOL_SPECS.
ALL_TOOLS: tuple[str, ...] = (
    "get_quote",
    "get_news",
    "get_company_info",
    "get_technicals",
    "get_levels",
    "get_holding",
    "get_deals",
    "get_research",
    "run_screener",
    "analyse_portfolio",
    "propose_ideas",
    "backtest_screener",
    "add_to_watchlist",
    "remember_fact",
)

# Per-intent allowlists. Keep these tight — the spirit of D8 is "fire
# fewer tools per turn, not more". If a list does not include `get_quote`
# the model literally cannot ask for a price on that turn.
SHORTLISTS: dict[str, tuple[str, ...]] = {
    "quote": ("get_quote",),
    "news": ("get_news", "get_quote"),
    "company_info": ("get_company_info", "get_quote"),
    "technicals": ("get_technicals", "get_levels", "get_quote"),
    "holding": ("get_holding", "get_deals"),
    "deals": ("get_deals", "get_holding"),
    "research": ("get_research",),
    "screener": ("run_screener",),
    "portfolio": ("analyse_portfolio",),
    "idea": ("propose_ideas", "run_screener", "get_technicals"),
    "backtest": ("backtest_screener",),
    # Advisory + education + other intentionally fall through to the
    # full catalog — these can legitimately want anything.
}


def shortlist_for(intent: str | None) -> tuple[str, ...] | None:
    """Return the tuple of tool names allowed for `intent`, or None
    to mean "no narrowing — pass the full catalog".
    """
    if not intent:
        return None
    return SHORTLISTS.get(intent)


def filter_tool_specs(
    tool_specs: list[dict[str, Any]],
    *,
    intent: str | None,
) -> list[dict[str, Any]]:
    """Return the subset of `tool_specs` whose function name is allowed
    for `intent`. If `intent` has no shortlist (advisory / education /
    other / unknown) we return the input list unchanged.
    """
    allowed = shortlist_for(intent)
    if allowed is None:
        return tool_specs
    allowed_set = set(allowed)
    return [
        spec
        for spec in tool_specs
        if spec.get("function", {}).get("name") in allowed_set
    ]
