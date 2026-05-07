"""Enums and constants for the Mr. Market stock universe."""

from enum import StrEnum


class RiskProfile(StrEnum):
    """User risk tolerance classification."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class SentimentLabel(StrEnum):
    """News / overall sentiment classification."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class TrendDirection(StrEnum):
    """Technical trend direction."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    SIDEWAYS = "sideways"


class DataSource(StrEnum):
    """Sources from which market data is ingested."""

    SCREENER = "screener"
    TICKERTAPE = "tickertape"
    MONEYCONTROL = "moneycontrol"
    NSE = "nse"
    BSE = "bse"
    YAHOO = "yahoo"
    GOOGLE_NEWS = "google_news"
    ECONOMIC_TIMES = "economic_times"
