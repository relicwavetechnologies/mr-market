"""Cross-validation engine.

Given N independent quote sources, compute a confidence-labelled price.

Rules:
- HIGH:  ≥3 valid sources AND max-pairwise spread ≤ 0.10%   → median
- MED:   ≥2 valid sources AND max-pairwise spread ≤ 0.50%   → median
- LOW:   anything else (fewer sources, or wider disagreement) → no price; show spread

The engine never picks a single number it isn't confident about. LOW returns
`price=None` and the caller is expected to surface the spread to the user.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from decimal import Decimal
from statistics import median
from typing import cast

from app.data.types import Confidence, Quote, QuoteSourceError, TriangulatedQuote

logger = logging.getLogger(__name__)


# Thresholds expressed as fractions, not percent.
HIGH_THRESHOLD = Decimal("0.001")  # 0.10 %
MED_THRESHOLD = Decimal("0.005")  # 0.50 %


def _max_pairwise_spread(prices: list[Decimal]) -> Decimal:
    """Largest |a-b|/min(a,b) across all pairs. Returns 0 for a single price."""
    if len(prices) < 2:
        return Decimal(0)
    lo = min(prices)
    hi = max(prices)
    if lo <= 0:
        return Decimal(0)
    return (hi - lo) / lo


def _classify(n_valid: int, spread: Decimal) -> Confidence:
    if n_valid >= 3 and spread <= HIGH_THRESHOLD:
        return Confidence.HIGH
    if n_valid >= 2 and spread <= MED_THRESHOLD:
        return Confidence.MED
    return Confidence.LOW


def _decimal_median(values: list[Decimal]) -> Decimal:
    # statistics.median works on floats; we want Decimal precision.
    s = sorted(values)
    n = len(s)
    if n == 0:
        raise ValueError("empty values")
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / Decimal(2)


def triangulate(quotes: list[Quote], failures: dict[str, str], ticker: str) -> TriangulatedQuote:
    """Pure function — combine fetched quotes into a TriangulatedQuote."""
    valid = [q for q in quotes if q.price is not None and q.price > 0]
    prices = [q.price for q in valid]

    spread = _max_pairwise_spread(prices)
    confidence = _classify(len(valid), spread)

    if confidence == Confidence.LOW:
        price: Decimal | None = None
        note = (
            f"Sources disagreed: {len(valid)} valid, "
            f"spread {spread * 100:.4f}%. Below MED threshold of "
            f"{MED_THRESHOLD * 100:.2f}%."
            if len(valid) >= 2
            else f"Only {len(valid)} valid source(s) — need at least 2."
        )
    else:
        price = _decimal_median(prices)
        note = None

    return TriangulatedQuote(
        ticker=ticker.upper(),
        price=price,
        confidence=confidence,
        spread_pct=spread * Decimal(100),
        sources=valid,
        failed_sources=dict(failures),
        as_of=datetime.now(timezone.utc),
        note=note,
    )


SourceFn = Callable[[str], Awaitable[Quote]]


async def fetch_all(
    ticker: str,
    sources: dict[str, SourceFn],
    *,
    timeout_s: float = 12.0,
) -> TriangulatedQuote:
    """Run every source in parallel; collect successes and failure reasons."""

    async def _safe(name: str, fn: SourceFn) -> tuple[str, Quote | Exception]:
        try:
            q = await asyncio.wait_for(fn(ticker), timeout=timeout_s)
            return name, q
        except (QuoteSourceError, asyncio.TimeoutError, Exception) as e:  # noqa: BLE001
            return name, e

    results = await asyncio.gather(*[_safe(n, fn) for n, fn in sources.items()])

    quotes: list[Quote] = []
    failures: dict[str, str] = {}
    for name, res in results:
        if isinstance(res, Quote):
            quotes.append(res)
        else:
            err = cast(Exception, res)
            failures[name] = str(err)
            logger.warning("source=%s ticker=%s failed: %s", name, ticker, err)

    return triangulate(quotes, failures, ticker)
