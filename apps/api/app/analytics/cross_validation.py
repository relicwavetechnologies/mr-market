"""Cross-source data validation for confidence scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    """Outcome of a cross-source validation check."""
    metric: str
    source_a: str
    source_b: str
    value_a: float
    value_b: float
    delta_pct: float
    confidence: str  # HIGH, MEDIUM, LOW


class CrossValidator:
    """Compare numeric data points across multiple sources.

    Confidence thresholds:
      - delta < 0.1 % --> HIGH confidence
      - 0.1 % <= delta < 1 % --> MEDIUM confidence
      - delta >= 1 % --> LOW (flag to user)
    """

    HIGH_THRESHOLD: float = 0.1
    MEDIUM_THRESHOLD: float = 1.0

    def validate_pair(
        self,
        metric: str,
        value_a: float,
        value_b: float,
        source_a: str = "source_a",
        source_b: str = "source_b",
    ) -> ValidationResult:
        """Compare two values for the same metric from different sources."""
        if value_b == 0 and value_a == 0:
            delta_pct = 0.0
        elif value_b == 0:
            delta_pct = 100.0
        else:
            delta_pct = abs(value_a - value_b) / abs(value_b) * 100

        confidence = self._classify(delta_pct)

        return ValidationResult(
            metric=metric,
            source_a=source_a,
            source_b=source_b,
            value_a=value_a,
            value_b=value_b,
            delta_pct=round(delta_pct, 4),
            confidence=confidence,
        )

    def validate_datasets(
        self,
        data_a: dict[str, Any],
        data_b: dict[str, Any],
        source_a: str = "source_a",
        source_b: str = "source_b",
    ) -> list[ValidationResult]:
        """Validate all overlapping numeric keys between two data dicts."""
        results: list[ValidationResult] = []

        common_keys = set(data_a.keys()) & set(data_b.keys())
        for key in sorted(common_keys):
            val_a = data_a[key]
            val_b = data_b[key]

            if not self._is_numeric(val_a) or not self._is_numeric(val_b):
                continue

            result = self.validate_pair(
                metric=key,
                value_a=float(val_a),
                value_b=float(val_b),
                source_a=source_a,
                source_b=source_b,
            )
            results.append(result)

        return results

    def overall_confidence(self, results: list[ValidationResult]) -> str:
        """Return the worst confidence level among all results."""
        if not results:
            return "HIGH"

        if any(r.confidence == "LOW" for r in results):
            return "LOW"
        if any(r.confidence == "MEDIUM" for r in results):
            return "MEDIUM"
        return "HIGH"

    def _classify(self, delta_pct: float) -> str:
        """Classify delta into confidence bucket."""
        if delta_pct < self.HIGH_THRESHOLD:
            return "HIGH"
        if delta_pct < self.MEDIUM_THRESHOLD:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _is_numeric(value: Any) -> bool:
        """Check if a value can be treated as a float."""
        if isinstance(value, (int, float)):
            return True
        if isinstance(value, str):
            try:
                float(value)
                return True
            except ValueError:
                return False
        return False
