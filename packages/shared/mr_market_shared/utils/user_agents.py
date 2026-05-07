"""User-agent string rotator for web scraping."""

import itertools
import random

_DEFAULT_USER_AGENTS: list[str] = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox on Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


class UserAgentRotator:
    """Rotates through a pool of user-agent strings for web scraping.

    Supports sequential round-robin and random selection modes.

    Usage:
        rotator = UserAgentRotator()
        headers = {"User-Agent": rotator.next()}
    """

    def __init__(
        self,
        user_agents: list[str] | None = None,
        *,
        shuffle: bool = True,
    ) -> None:
        pool = list(user_agents or _DEFAULT_USER_AGENTS)
        if shuffle:
            random.shuffle(pool)
        self._pool = pool
        self._cycle = itertools.cycle(self._pool)

    @property
    def pool_size(self) -> int:
        """Number of user-agent strings in the pool."""
        return len(self._pool)

    def next(self) -> str:
        """Return the next user-agent string in round-robin order."""
        return next(self._cycle)

    def random(self) -> str:
        """Return a random user-agent string from the pool."""
        return random.choice(self._pool)
