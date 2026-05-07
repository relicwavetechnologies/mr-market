"""Technical analysis engine wrapping pandas-ta indicators."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


class TechnicalAnalyzer:
    """Compute standard technical indicators from OHLCV DataFrames.

    Expects a DataFrame with columns: open, high, low, close, volume.
    """

    def compute_all(self, df: pd.DataFrame) -> dict[str, Any]:
        """Compute a full suite of indicators and return as a flat dict.

        Indicators: RSI-14, MACD (12/26/9), Bollinger Bands (20,2),
        SMA-20/50/200, EMA-20, Pivot Points, ATR-14.
        """
        result: dict[str, Any] = {}

        close = df["close"]
        high = df["high"]
        low = df["low"]

        # RSI (14)
        result["rsi_14"] = self._rsi(close, period=14)

        # MACD (12, 26, 9)
        macd_line, signal_line = self._macd(close)
        result["macd"] = macd_line
        result["macd_signal"] = signal_line

        # Bollinger Bands (20, 2)
        bb_upper, bb_lower = self._bollinger_bands(close, period=20, std_dev=2)
        result["bb_upper"] = bb_upper
        result["bb_lower"] = bb_lower

        # Simple Moving Averages
        result["sma_20"] = self._sma(close, 20)
        result["sma_50"] = self._sma(close, 50)
        result["sma_200"] = self._sma(close, 200)

        # Exponential Moving Average
        result["ema_20"] = self._ema(close, 20)

        # Pivot Points (Classic)
        pivot, s1, s2, r1, r2 = self._pivot_points(high, low, close)
        result["pivot"] = pivot
        result["support_1"] = s1
        result["support_2"] = s2
        result["resistance_1"] = r1
        result["resistance_2"] = r2

        # ATR (14)
        result["atr"] = self._atr(high, low, close, period=14)

        # Round everything
        for key, val in result.items():
            if isinstance(val, float) and not np.isnan(val):
                result[key] = round(val, 2)
            elif val is None or (isinstance(val, float) and np.isnan(val)):
                result[key] = None

        return result

    def detect_trend(self, df: pd.DataFrame) -> str:
        """Classify the current trend as bullish, bearish, or sideways.

        Uses SMA-20 vs SMA-50 crossover and RSI zones.
        """
        close = df["close"]
        sma_20 = self._sma(close, 20)
        sma_50 = self._sma(close, 50)
        rsi = self._rsi(close, 14)

        if sma_20 is None or sma_50 is None:
            return "sideways"

        last_close = float(close.iloc[-1])

        if sma_20 > sma_50 and last_close > sma_20:
            if rsi is not None and rsi > 70:
                return "bullish"  # strongly bullish
            return "bullish"

        if sma_20 < sma_50 and last_close < sma_20:
            if rsi is not None and rsi < 30:
                return "bearish"  # strongly bearish
            return "bearish"

        return "sideways"

    # ------------------------------------------------------------------
    # Indicator implementations
    # ------------------------------------------------------------------

    @staticmethod
    def _rsi(close: pd.Series, period: int = 14) -> float | None:
        """Relative Strength Index."""
        if len(close) < period + 1:
            return None

        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)

        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))

        last_rsi = rsi.iloc[-1]
        return float(last_rsi) if not np.isnan(last_rsi) else None

    @staticmethod
    def _macd(
        close: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> tuple[float | None, float | None]:
        """MACD line and signal line."""
        if len(close) < slow + signal:
            return None, None

        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()

        m = float(macd_line.iloc[-1])
        s = float(signal_line.iloc[-1])
        return (
            m if not np.isnan(m) else None,
            s if not np.isnan(s) else None,
        )

    @staticmethod
    def _bollinger_bands(
        close: pd.Series,
        period: int = 20,
        std_dev: int = 2,
    ) -> tuple[float | None, float | None]:
        """Upper and lower Bollinger Bands."""
        if len(close) < period:
            return None, None

        sma = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()

        upper = float((sma + std_dev * std).iloc[-1])
        lower = float((sma - std_dev * std).iloc[-1])

        return (
            upper if not np.isnan(upper) else None,
            lower if not np.isnan(lower) else None,
        )

    @staticmethod
    def _sma(close: pd.Series, period: int) -> float | None:
        """Simple Moving Average."""
        if len(close) < period:
            return None
        val = float(close.rolling(window=period).mean().iloc[-1])
        return val if not np.isnan(val) else None

    @staticmethod
    def _ema(close: pd.Series, period: int) -> float | None:
        """Exponential Moving Average."""
        if len(close) < period:
            return None
        val = float(close.ewm(span=period, adjust=False).mean().iloc[-1])
        return val if not np.isnan(val) else None

    @staticmethod
    def _pivot_points(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
    ) -> tuple[float | None, float | None, float | None, float | None, float | None]:
        """Classic pivot points from the last candle."""
        h = float(high.iloc[-1])
        l = float(low.iloc[-1])
        c = float(close.iloc[-1])

        pivot = (h + l + c) / 3
        s1 = 2 * pivot - h
        s2 = pivot - (h - l)
        r1 = 2 * pivot - l
        r2 = pivot + (h - l)

        return pivot, s1, s2, r1, r2

    @staticmethod
    def _atr(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14,
    ) -> float | None:
        """Average True Range."""
        if len(close) < period + 1:
            return None

        prev_close = close.shift(1)
        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)

        atr_series = tr.rolling(window=period).mean()
        val = float(atr_series.iloc[-1])
        return val if not np.isnan(val) else None
