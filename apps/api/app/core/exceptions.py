"""Custom application exceptions."""

from __future__ import annotations


class MrMarketError(Exception):
    """Base exception for all Mr. Market application errors."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class TickerNotFoundError(MrMarketError):
    """Raised when a requested ticker does not exist in the universe."""

    def __init__(self, ticker: str) -> None:
        super().__init__(
            f"Ticker '{ticker}' not found in the stock universe. "
            "Please check the symbol and try again.",
            code="TICKER_NOT_FOUND",
        )
        self.ticker = ticker


class DataStaleError(MrMarketError):
    """Raised when the available data is too old to be reliable."""

    def __init__(self, ticker: str, data_type: str, age_hours: float) -> None:
        super().__init__(
            f"{data_type} data for '{ticker}' is {age_hours:.1f} hours old "
            "and may be unreliable.",
            code="DATA_STALE",
        )
        self.ticker = ticker
        self.data_type = data_type
        self.age_hours = age_hours


class LLMError(MrMarketError):
    """Raised when the LLM provider returns an error or times out."""

    def __init__(self, provider: str, detail: str) -> None:
        super().__init__(
            f"LLM provider '{provider}' error: {detail}",
            code="LLM_ERROR",
        )
        self.provider = provider


class ScraperError(MrMarketError):
    """Raised when a scraper pipeline fails."""

    def __init__(self, scraper_name: str, detail: str) -> None:
        super().__init__(
            f"Scraper '{scraper_name}' failed: {detail}",
            code="SCRAPER_ERROR",
        )
        self.scraper_name = scraper_name


class RateLimitError(MrMarketError):
    """Raised when a rate limit is exceeded (API or scraper)."""

    def __init__(self, resource: str, retry_after_seconds: int | None = None) -> None:
        msg = f"Rate limit exceeded for '{resource}'."
        if retry_after_seconds is not None:
            msg += f" Retry after {retry_after_seconds}s."
        super().__init__(msg, code="RATE_LIMITED")
        self.resource = resource
        self.retry_after_seconds = retry_after_seconds
