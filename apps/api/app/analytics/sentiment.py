"""Sentiment analysis wrapping a FinBERT transformer model."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SentimentResult:
    """Output of a single sentiment classification."""
    label: str  # "positive", "negative", "neutral"
    score: float  # confidence 0..1


class SentimentAnalyzer:
    """Classify financial headlines using a FinBERT model.

    Loads the model lazily on first call to keep startup fast.  Falls back
    to a keyword-based heuristic if ``transformers`` is not installed.
    """

    _MODEL_NAME = "ProsusAI/finbert"

    def __init__(self) -> None:
        self._pipeline: Any = None
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazy-load the transformer pipeline."""
        if self._loaded:
            return
        try:
            from transformers import pipeline  # type: ignore[import-untyped]

            self._pipeline = pipeline(
                "sentiment-analysis",
                model=self._MODEL_NAME,
                tokenizer=self._MODEL_NAME,
                truncation=True,
                max_length=512,
            )
            self._loaded = True
            logger.info("FinBERT model loaded successfully")
        except ImportError:
            logger.warning(
                "transformers not installed — falling back to keyword heuristic"
            )
            self._loaded = True  # don't retry

    def analyze(self, headline: str) -> SentimentResult:
        """Classify a single headline."""
        self._ensure_loaded()

        if self._pipeline is not None:
            result = self._pipeline(headline)[0]
            return SentimentResult(
                label=result["label"].lower(),
                score=round(float(result["score"]), 4),
            )

        return self._keyword_fallback(headline)

    def analyze_batch(self, headlines: list[str]) -> list[SentimentResult]:
        """Classify multiple headlines in a single batch."""
        self._ensure_loaded()

        if self._pipeline is not None and headlines:
            raw_results = self._pipeline(headlines)
            return [
                SentimentResult(
                    label=r["label"].lower(),
                    score=round(float(r["score"]), 4),
                )
                for r in raw_results
            ]

        return [self._keyword_fallback(h) for h in headlines]

    # ------------------------------------------------------------------
    # Keyword fallback
    # ------------------------------------------------------------------

    _POSITIVE = {
        "surge", "rally", "gain", "rise", "jump", "soar", "bull",
        "upgrade", "buy", "outperform", "beat", "profit", "growth",
        "dividend", "record", "strong", "positive", "optimistic",
    }

    _NEGATIVE = {
        "fall", "drop", "crash", "decline", "loss", "bear", "sell",
        "downgrade", "weak", "negative", "concern", "risk", "debt",
        "default", "fraud", "penalty", "slump", "cut", "miss",
        "lower circuit", "plunge",
    }

    @classmethod
    def _keyword_fallback(cls, headline: str) -> SentimentResult:
        """Simple keyword-based sentiment when FinBERT is unavailable."""
        words = set(headline.lower().split())
        pos_hits = len(words & cls._POSITIVE)
        neg_hits = len(words & cls._NEGATIVE)

        if pos_hits > neg_hits:
            return SentimentResult(label="positive", score=0.6)
        if neg_hits > pos_hits:
            return SentimentResult(label="negative", score=0.6)
        return SentimentResult(label="neutral", score=0.5)
