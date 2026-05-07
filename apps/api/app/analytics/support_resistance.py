"""Support and resistance level detection using pivot points and Fibonacci."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class SRLevel:
    """A single support or resistance level."""
    price: float
    type: str  # "support" or "resistance"
    method: str  # "pivot" or "fibonacci"
    strength: str  # "strong", "moderate", "weak"


class SupportResistanceDetector:
    """Identify key support and resistance levels from historical price data.

    Combines two methods:
      1. **Classic Pivot Points** — derived from the most recent trading day.
      2. **Fibonacci Retracements** — derived from the recent swing high/low
         over a configurable lookback period.
    """

    def __init__(self, lookback_days: int = 60) -> None:
        self._lookback = lookback_days

    def detect(self, df: pd.DataFrame) -> list[SRLevel]:
        """Return an ordered list of S/R levels from the price DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Must contain ``high``, ``low``, ``close`` columns.
        """
        levels: list[SRLevel] = []
        levels.extend(self._pivot_levels(df))
        levels.extend(self._fibonacci_levels(df))
        levels.sort(key=lambda lvl: lvl.price)
        return levels

    def to_dict(self, df: pd.DataFrame) -> dict[str, Any]:
        """Convenience wrapper returning a JSON-serialisable dict."""
        levels = self.detect(df)
        current_price = float(df["close"].iloc[-1])

        supports = [l for l in levels if l.type == "support"]
        resistances = [l for l in levels if l.type == "resistance"]

        return {
            "current_price": round(current_price, 2),
            "supports": [
                {"price": round(l.price, 2), "method": l.method, "strength": l.strength}
                for l in supports
            ],
            "resistances": [
                {"price": round(l.price, 2), "method": l.method, "strength": l.strength}
                for l in resistances
            ],
        }

    # ------------------------------------------------------------------
    # Pivot Points
    # ------------------------------------------------------------------

    @staticmethod
    def _pivot_levels(df: pd.DataFrame) -> list[SRLevel]:
        """Classic pivot points from the last candle."""
        h = float(df["high"].iloc[-1])
        l = float(df["low"].iloc[-1])
        c = float(df["close"].iloc[-1])

        pivot = (h + l + c) / 3
        s1 = 2 * pivot - h
        s2 = pivot - (h - l)
        s3 = l - 2 * (h - pivot)
        r1 = 2 * pivot - l
        r2 = pivot + (h - l)
        r3 = h + 2 * (pivot - l)

        return [
            SRLevel(price=s3, type="support", method="pivot", strength="weak"),
            SRLevel(price=s2, type="support", method="pivot", strength="moderate"),
            SRLevel(price=s1, type="support", method="pivot", strength="strong"),
            SRLevel(price=r1, type="resistance", method="pivot", strength="strong"),
            SRLevel(price=r2, type="resistance", method="pivot", strength="moderate"),
            SRLevel(price=r3, type="resistance", method="pivot", strength="weak"),
        ]

    # ------------------------------------------------------------------
    # Fibonacci Retracements
    # ------------------------------------------------------------------

    def _fibonacci_levels(self, df: pd.DataFrame) -> list[SRLevel]:
        """Fibonacci retracement levels from the recent swing range."""
        window = df.tail(self._lookback)
        swing_high = float(window["high"].max())
        swing_low = float(window["low"].min())
        diff = swing_high - swing_low

        if diff < 0.01:
            return []

        fib_ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
        current_price = float(df["close"].iloc[-1])

        levels: list[SRLevel] = []
        for ratio in fib_ratios:
            level = swing_high - diff * ratio

            # Classify strength by proximity to key Fibonacci ratios
            if ratio in (0.382, 0.618):
                strength = "strong"
            elif ratio == 0.5:
                strength = "moderate"
            else:
                strength = "weak"

            sr_type = "support" if level < current_price else "resistance"
            levels.append(SRLevel(
                price=level,
                type=sr_type,
                method="fibonacci",
                strength=strength,
            ))

        return levels
