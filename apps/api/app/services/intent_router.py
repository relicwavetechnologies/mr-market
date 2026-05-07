"""Intent classification for user queries."""

from __future__ import annotations

import re
from enum import Enum


class Intent(Enum):
    """Possible user intents recognised by the router."""

    STOCK_PRICE = "stock_price"
    STOCK_ANALYSIS = "stock_analysis"
    WHY_MOVING = "why_moving"
    SCREENER = "screener"
    PORTFOLIO = "portfolio"
    GENERAL = "general"


# ---------------------------------------------------------------------------
# Keyword patterns — ordered by priority (first match wins)
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[Intent, re.Pattern[str]]] = [
    (
        Intent.WHY_MOVING,
        re.compile(
            r"\b(why\s+is|why\s+are|reason\s+for|what\s+caused|"
            r"falling|rising|crashing|surging|tanking|rallying|"
            r"upper\s+circuit|lower\s+circuit)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.SCREENER,
        re.compile(
            r"\b(screen|filter|show\s+me\s+stocks|stocks?\s+with|"
            r"rsi\s*[<>]|roe\s*[<>]|pe\s*[<>]|"
            r"oversold|overbought|undervalued)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.PORTFOLIO,
        re.compile(
            r"\b(portfolio|my\s+holdings|my\s+stocks|rebalance|"
            r"review\s+my|allocation)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.STOCK_ANALYSIS,
        re.compile(
            r"\b(analy[sz]e|analysis|trade\s+setup|technical\s+analysis|"
            r"fundamental|buy\s+or\s+sell|entry|target|stop\s*loss|"
            r"support\s+and\s+resistance|should\s+i\s+buy|"
            r"give\s+me\s+a\s+view|outlook|what\s+do\s+you\s+think)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.STOCK_PRICE,
        re.compile(
            r"\b(price|cmp|current\s+market\s+price|"
            r"what\'?s?\s+(?:the\s+)?price|how\s+much\s+is|"
            r"quote|ltp|last\s+traded)\b",
            re.IGNORECASE,
        ),
    ),
]


class IntentRouter:
    """Classify user queries into actionable intents.

    Uses keyword / regex matching for the MVP.  Can be swapped with a
    DistilBERT classifier later by overriding ``classify``.
    """

    def classify(self, query: str) -> Intent:
        """Return the highest-priority intent that matches *query*.

        Falls back to ``Intent.GENERAL`` if no pattern matches.
        """
        normalised = query.strip()
        for intent, pattern in _PATTERNS:
            if pattern.search(normalised):
                return intent
        return Intent.GENERAL
