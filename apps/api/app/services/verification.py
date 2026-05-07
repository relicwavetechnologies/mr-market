"""Anti-hallucination verification pass for LLM-generated responses."""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Regex to find numeric claims in text, e.g. "P/E of 23.4", "RSI is 68.2"
_NUMERIC_CLAIM_RE = re.compile(
    r"(?P<label>"
    r"(?:P/?E|PE|ROE|ROCE|RSI|MACD|EPS|book\s+value|"
    r"debt[/-]equity|D/?E|revenue\s+growth|profit\s+growth|"
    r"dividend\s+yield|ATR|SMA|EMA|support|resistance|"
    r"promoter|FII|DII|retail|close|open|high|low|price|"
    r"market\s+cap|volume)"
    r")"
    r"[\s:=~of]*?"
    r"(?:(?:is|at|of|around|approximately|~)\s*)?"
    r"(?:(?:INR|Rs\.?|₹)\s*)?"
    r"(?P<value>[\d,]+\.?\d*)\s*%?",
    re.IGNORECASE,
)

# Maps claim labels (lower-cased) to possible keys in source data.
_LABEL_KEY_MAP: dict[str, list[str]] = {
    "pe": ["pe"],
    "p/e": ["pe"],
    "roe": ["roe"],
    "roce": ["roce"],
    "rsi": ["rsi_14"],
    "macd": ["macd"],
    "eps": ["eps"],
    "book value": ["book_value"],
    "debt/equity": ["debt_equity"],
    "d/e": ["debt_equity"],
    "debt-equity": ["debt_equity"],
    "revenue growth": ["revenue_growth_pct"],
    "profit growth": ["profit_growth_pct"],
    "dividend yield": ["dividend_yield_pct"],
    "atr": ["atr"],
    "sma": ["sma_20", "sma_50", "sma_200"],
    "ema": ["ema_20"],
    "support": ["support_1", "support_2"],
    "resistance": ["resistance_1", "resistance_2"],
    "promoter": ["promoter_pct"],
    "fii": ["fii_pct"],
    "dii": ["dii_pct"],
    "retail": ["retail_pct"],
    "close": ["close"],
    "open": ["open"],
    "high": ["high"],
    "low": ["low"],
    "price": ["close"],
    "market cap": ["market_cap"],
}


@dataclass
class VerificationResult:
    """Outcome of the verification pass."""

    status: str  # "ACCEPT" or "REJECT"
    details: list[str] = field(default_factory=list)
    checked_claims: int = 0
    failed_claims: int = 0


class VerificationService:
    """Extract numeric claims from LLM output and cross-check against sources.

    A claim is **rejected** if the LLM-stated value deviates by more than
    2 % from the source value.  If any claim is rejected the entire response
    is flagged as ``REJECT``.
    """

    TOLERANCE_PCT: float = 2.0

    def verify(
        self,
        llm_output: str,
        source_data: dict[str, Any],
    ) -> VerificationResult:
        """Run verification and return an ACCEPT or REJECT result."""
        claims = self._extract_claims(llm_output)
        flat_source = self._flatten_source(source_data)

        result = VerificationResult(status="ACCEPT", checked_claims=len(claims))

        for label, claimed_value in claims:
            source_keys = _LABEL_KEY_MAP.get(label.lower().strip(), [])
            for key in source_keys:
                source_val = flat_source.get(key)
                if source_val is None:
                    continue

                try:
                    source_num = float(source_val)
                except (ValueError, TypeError):
                    continue

                if source_num == 0:
                    if claimed_value != 0:
                        result.details.append(
                            f"{label}: LLM said {claimed_value} but source is 0"
                        )
                        result.failed_claims += 1
                    continue

                deviation = abs(claimed_value - source_num) / abs(source_num) * 100
                if deviation > self.TOLERANCE_PCT:
                    result.details.append(
                        f"{label}: LLM said {claimed_value:.2f}, "
                        f"source says {source_num:.2f} "
                        f"(deviation {deviation:.1f}%)"
                    )
                    result.failed_claims += 1

        if result.failed_claims > 0:
            result.status = "REJECT"

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_claims(text: str) -> list[tuple[str, float]]:
        """Parse numeric claims from the LLM response text."""
        claims: list[tuple[str, float]] = []
        for match in _NUMERIC_CLAIM_RE.finditer(text):
            label = match.group("label")
            raw_value = match.group("value").replace(",", "")
            try:
                value = float(raw_value)
                claims.append((label, value))
            except ValueError:
                continue
        return claims

    @staticmethod
    def _flatten_source(source_data: dict[str, Any]) -> dict[str, Any]:
        """Flatten nested source data into a single-level dict."""
        flat: dict[str, Any] = {}
        data = source_data.get("data", source_data)
        for section_key, section in data.items():
            if isinstance(section, dict):
                for k, v in section.items():
                    if k not in ("source", "error", "timestamp"):
                        flat[k] = v
        return flat
