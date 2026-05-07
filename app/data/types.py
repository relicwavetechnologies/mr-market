"""Shared types for the data layer (quote sources + triangulation)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Literal


class Confidence(str, Enum):
    HIGH = "HIGH"
    MED = "MED"
    LOW = "LOW"


SourceName = Literal["nselib", "yfinance", "screener", "moneycontrol"]


@dataclass(slots=True, frozen=True)
class Quote:
    """A single-source price snapshot for one ticker.

    Frozen + slots for cheap equality and predictable serialisation.
    """

    ticker: str
    price: Decimal
    source: SourceName
    fetched_at: datetime
    prev_close: Decimal | None = None
    day_open: Decimal | None = None
    day_high: Decimal | None = None
    day_low: Decimal | None = None
    volume: int | None = None
    extras: dict[str, str] = field(default_factory=dict)

    @property
    def change_pct(self) -> Decimal | None:
        if self.prev_close is None or self.prev_close == 0:
            return None
        return ((self.price - self.prev_close) / self.prev_close) * Decimal(100)


@dataclass(slots=True)
class TriangulatedQuote:
    """Cross-validated quote across multiple sources."""

    ticker: str
    price: Decimal | None
    confidence: Confidence
    spread_pct: Decimal
    sources: list[Quote]
    failed_sources: dict[str, str]  # name -> error
    as_of: datetime
    note: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "ticker": self.ticker,
            "price": str(self.price) if self.price is not None else None,
            "confidence": self.confidence.value,
            "spread_pct": f"{self.spread_pct:.4f}",
            "as_of": self.as_of.astimezone(timezone.utc).isoformat(),
            "sources": [
                {
                    "name": q.source,
                    "price": str(q.price),
                    "fetched_at": q.fetched_at.astimezone(timezone.utc).isoformat(),
                    "prev_close": str(q.prev_close) if q.prev_close is not None else None,
                    "day_open": str(q.day_open) if q.day_open is not None else None,
                    "day_high": str(q.day_high) if q.day_high is not None else None,
                    "day_low": str(q.day_low) if q.day_low is not None else None,
                    "volume": q.volume,
                    "change_pct": (
                        f"{q.change_pct:.4f}" if q.change_pct is not None else None
                    ),
                }
                for q in self.sources
            ],
            "failed_sources": self.failed_sources,
            "note": self.note,
        }


class QuoteSourceError(Exception):
    """Raised by an individual source when it fails to produce a quote."""
