"""FinBERT-based sentiment analysis pipeline for financial news.

Loads the ProsusAI/finbert model from HuggingFace and processes news
headlines in batches. Returns sentiment labels (positive / negative /
neutral) with confidence scores.

Benchmark: ~81% accuracy on financial headline sentiment classification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# FinBERT model from HuggingFace
FINBERT_MODEL = "ProsusAI/finbert"

# Label mapping from FinBERT output indices
_LABEL_MAP: dict[int, str] = {
    0: "positive",
    1: "negative",
    2: "neutral",
}


@dataclass
class SentimentResult:
    """Result of sentiment analysis for a single headline."""

    headline: str
    label: str  # positive / negative / neutral
    score: float  # confidence score (0.0 - 1.0)
    scores: dict[str, float] = field(default_factory=dict)  # all class probabilities


class SentimentPipeline:
    """FinBERT sentiment classifier for financial news headlines.

    Usage::

        pipeline = SentimentPipeline()
        pipeline.load_model()
        results = pipeline.analyze_batch(["Markets rally on strong earnings"])
    """

    def __init__(
        self,
        model_name: str = FINBERT_MODEL,
        batch_size: int = 32,
        device: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._tokenizer: AutoTokenizer | None = None
        self._model: AutoModelForSequenceClassification | None = None
        self._loaded = False

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    def load_model(self) -> None:
        """Download and load the FinBERT model and tokenizer."""
        if self._loaded:
            return
        logger.info("sentiment: loading FinBERT model %s on %s", self.model_name, self._device)
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        self._model.to(self._device)  # type: ignore[union-attr]
        self._model.eval()  # type: ignore[union-attr]
        self._loaded = True
        logger.info("sentiment: FinBERT model loaded successfully")

    def unload_model(self) -> None:
        """Release model from memory."""
        self._model = None
        self._tokenizer = None
        self._loaded = False
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.info("sentiment: model unloaded")

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def analyze(self, headline: str) -> SentimentResult:
        """Analyze sentiment of a single headline."""
        results = self.analyze_batch([headline])
        return results[0]

    def analyze_batch(self, headlines: list[str]) -> list[SentimentResult]:
        """Analyze sentiment for a batch of headlines.

        Parameters
        ----------
        headlines:
            List of news headline strings.

        Returns
        -------
        list[SentimentResult]
            Sentiment label and confidence for each headline.
        """
        if not self._loaded:
            self.load_model()
        assert self._tokenizer is not None
        assert self._model is not None

        all_results: list[SentimentResult] = []

        for i in range(0, len(headlines), self.batch_size):
            batch = headlines[i : i + self.batch_size]
            inputs = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(self._device)

            with torch.no_grad():
                outputs = self._model(**inputs)
                probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)

            for j, headline in enumerate(batch):
                probs = probabilities[j].cpu().tolist()
                predicted_idx = int(torch.argmax(probabilities[j]).item())
                label = _LABEL_MAP.get(predicted_idx, "neutral")
                confidence = probs[predicted_idx]

                all_results.append(
                    SentimentResult(
                        headline=headline,
                        label=label,
                        score=round(confidence, 4),
                        scores={
                            "positive": round(probs[0], 4),
                            "negative": round(probs[1], 4),
                            "neutral": round(probs[2], 4),
                        },
                    )
                )

        logger.info("sentiment: analysed %d headlines", len(all_results))
        return all_results

    # ------------------------------------------------------------------
    # Pipeline interface
    # ------------------------------------------------------------------

    def run(self, headlines: list[str]) -> list[dict[str, Any]]:
        """Run the sentiment pipeline and return serialisable results.

        This is the main entry point used by Celery tasks.
        """
        results = self.analyze_batch(headlines)
        return [
            {
                "headline": r.headline,
                "sentiment_label": r.label,
                "sentiment_score": r.score,
                "scores": r.scores,
            }
            for r in results
        ]
