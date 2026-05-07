"""Sentiment scoring for news headlines.

Uses VADER (rule-based, pure-Python, ~1 ms per headline). VADER is solid on
short news headlines and needs zero model download / GPU.

Returns a normalised compound score in [-1, +1] and a coarse label
(positive | negative | neutral).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

Label = Literal["positive", "negative", "neutral"]


@dataclass(slots=True, frozen=True)
class SentimentResult:
    score: Decimal      # compound, in [-1, +1]
    label: Label


@lru_cache(maxsize=1)
def _analyzer() -> SentimentIntensityAnalyzer:
    return SentimentIntensityAnalyzer()


def score(text: str) -> SentimentResult:
    if not text or not text.strip():
        return SentimentResult(score=Decimal(0), label="neutral")
    raw = _analyzer().polarity_scores(text)
    compound = float(raw.get("compound", 0.0))
    if compound >= 0.05:
        label: Label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"
    return SentimentResult(score=Decimal(str(round(compound, 4))), label=label)
