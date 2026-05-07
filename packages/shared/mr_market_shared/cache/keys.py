"""Redis cache key patterns and TTLs for Mr. Market."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CacheEntry:
    """A cache key paired with its TTL in seconds."""

    key: str
    ttl: int  # seconds; 0 means persist (no expiry)


class CacheKeys:
    """Static methods for generating Redis cache keys with associated TTLs.

    TTL values are based on the data freshness requirements:
    - price:{ticker}              -> 5 sec   (real-time quotes)
    - ohlc:{ticker}:{date}        -> 24 hr   (daily candles, immutable once closed)
    - fundamentals:{ticker}       -> 24 hr   (scraped once/day)
    - technicals:{ticker}         -> 1 min   (computed frequently)
    - news:{ticker}:latest        -> 5 min   (news feed)
    - sentiment:{ticker}          -> 5 min   (derived from news)
    - holding:{ticker}            -> 7 days  (quarterly data)
    - llm_response:{query_hash}   -> 1 hr    (LLM answer cache)
    - scraper:health:{source}     -> persist (health-check flag)
    """

    # TTL constants (seconds)
    TTL_PRICE = 5
    TTL_OHLC = 86_400           # 24 hours
    TTL_FUNDAMENTALS = 86_400   # 24 hours
    TTL_TECHNICALS = 60         # 1 minute
    TTL_NEWS = 300              # 5 minutes
    TTL_SENTIMENT = 300         # 5 minutes
    TTL_HOLDING = 604_800       # 7 days
    TTL_LLM_RESPONSE = 3_600   # 1 hour
    TTL_SCRAPER_HEALTH = 0     # persist (no expiry)

    @staticmethod
    def price(ticker: str) -> CacheEntry:
        """Real-time price quote for a ticker."""
        return CacheEntry(key=f"price:{ticker}", ttl=CacheKeys.TTL_PRICE)

    @staticmethod
    def ohlc(ticker: str, date: str) -> CacheEntry:
        """Daily OHLCV candle for a ticker on a specific date."""
        return CacheEntry(key=f"ohlc:{ticker}:{date}", ttl=CacheKeys.TTL_OHLC)

    @staticmethod
    def fundamentals(ticker: str) -> CacheEntry:
        """Fundamental data for a ticker."""
        return CacheEntry(key=f"fundamentals:{ticker}", ttl=CacheKeys.TTL_FUNDAMENTALS)

    @staticmethod
    def technicals(ticker: str) -> CacheEntry:
        """Technical indicators for a ticker."""
        return CacheEntry(key=f"technicals:{ticker}", ttl=CacheKeys.TTL_TECHNICALS)

    @staticmethod
    def news_latest(ticker: str) -> CacheEntry:
        """Latest news articles for a ticker."""
        return CacheEntry(key=f"news:{ticker}:latest", ttl=CacheKeys.TTL_NEWS)

    @staticmethod
    def sentiment(ticker: str) -> CacheEntry:
        """Aggregated sentiment for a ticker."""
        return CacheEntry(key=f"sentiment:{ticker}", ttl=CacheKeys.TTL_SENTIMENT)

    @staticmethod
    def holding(ticker: str) -> CacheEntry:
        """Shareholding pattern for a ticker."""
        return CacheEntry(key=f"holding:{ticker}", ttl=CacheKeys.TTL_HOLDING)

    @staticmethod
    def llm_response(query_hash: str) -> CacheEntry:
        """Cached LLM response for a query hash."""
        return CacheEntry(key=f"llm_response:{query_hash}", ttl=CacheKeys.TTL_LLM_RESPONSE)

    @staticmethod
    def scraper_health(source: str) -> CacheEntry:
        """Health-check flag for a scraper source (persisted)."""
        return CacheEntry(key=f"scraper:health:{source}", ttl=CacheKeys.TTL_SCRAPER_HEALTH)
