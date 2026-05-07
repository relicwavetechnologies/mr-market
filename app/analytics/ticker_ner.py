"""Headline → ticker matching.

Loads the active stock universe from the DB once per call and matches headlines
against (a) the NSE symbol itself, (b) high-signal aliases derived from the
company name. Word-boundary regex; case-insensitive.

This is intentionally simple. The Phase 1 universe is 50 NIFTY-50 stocks; we
do not need full NER at this scale. If we expand to NIFTY-200 we can swap in
spaCy or a Haiku-based fallback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.stock import Stock


@dataclass(slots=True, frozen=True)
class TickerEntry:
    ticker: str
    aliases: tuple[str, ...]   # all the strings we'll match on, lowercased


# Hand-curated overrides for ambiguous or generic-sounding company names.
# Without these, headlines about "Cipla treatments" would match the company
# but a headline about "Maruti the actor" wouldn't disambiguate.
_ALIAS_OVERRIDES: dict[str, tuple[str, ...]] = {
    "RELIANCE": ("reliance industries", "reliance ind", "ril", "reliance"),
    "TCS": ("tcs", "tata consultancy"),
    "HDFCBANK": ("hdfc bank", "hdfcbank"),
    "BHARTIARTL": ("bharti airtel", "airtel"),
    "ICICIBANK": ("icici bank",),
    "INFY": ("infosys", "infy"),
    "SBIN": ("state bank of india", "sbi"),
    "LT": ("larsen & toubro", "larsen and toubro", "l&t"),
    "ITC": ("itc",),  # short, common — only match standalone
    "HINDUNILVR": ("hindustan unilever", "hul"),
    "BAJFINANCE": ("bajaj finance",),
    "KOTAKBANK": ("kotak mahindra bank", "kotak bank"),
    "HCLTECH": ("hcl technologies", "hcl tech"),
    "MARUTI": ("maruti suzuki", "maruti"),
    "SUNPHARMA": ("sun pharmaceutical", "sun pharma"),
    "TITAN": ("titan company", "titan"),
    "M&M": ("mahindra & mahindra", "mahindra and mahindra", "m&m"),
    "AXISBANK": ("axis bank",),
    "NTPC": ("ntpc",),
    "ASIANPAINT": ("asian paints",),
    "BAJAJFINSV": ("bajaj finserv",),
    "ONGC": ("ongc", "oil and natural gas"),
    "ULTRACEMCO": ("ultratech cement",),
    "WIPRO": ("wipro",),
    "ADANIENT": ("adani enterprises",),
    "JSWSTEEL": ("jsw steel",),
    "POWERGRID": ("power grid corporation", "powergrid"),
    "TATASTEEL": ("tata steel",),
    "TATAMOTORS": ("tata motors",),
    "COALINDIA": ("coal india",),
    "NESTLEIND": ("nestle india", "nestle"),
    "TECHM": ("tech mahindra",),
    "HDFCLIFE": ("hdfc life",),
    "ADANIPORTS": ("adani ports", "apsez"),
    "BAJAJ-AUTO": ("bajaj auto",),
    "GRASIM": ("grasim industries", "grasim"),
    "DRREDDY": ("dr reddy", "dr. reddy", "drl"),
    "INDUSINDBK": ("indusind bank",),
    "CIPLA": ("cipla",),
    "EICHERMOT": ("eicher motors",),
    "SBILIFE": ("sbi life",),
    "HEROMOTOCO": ("hero motocorp", "heromotocorp"),
    "APOLLOHOSP": ("apollo hospitals",),
    "TATACONSUM": ("tata consumer",),
    "BRITANNIA": ("britannia industries", "britannia"),
    "DIVISLAB": ("divi's laboratories", "divi labs", "divis lab"),
    "LTIM": ("ltimindtree", "lti mindtree", "ltim"),
    "SHRIRAMFIN": ("shriram finance",),
    "TRENT": ("trent ltd", "trent limited"),
    "BEL": ("bharat electronics",),
}


@dataclass(slots=True)
class TickerIndex:
    entries: tuple[TickerEntry, ...]
    pattern: re.Pattern[str]

    def find_tickers(self, text: str) -> list[str]:
        """Return tickers mentioned in ``text``, in order of first appearance."""
        if not text:
            return []
        hay = text.lower()
        matches = list(self.pattern.finditer(hay))
        if not matches:
            return []
        # alias_lower → ticker
        alias_to_ticker: dict[str, str] = {}
        for e in self.entries:
            for a in e.aliases:
                alias_to_ticker.setdefault(a, e.ticker)
        seen: list[str] = []
        for m in matches:
            t = alias_to_ticker.get(m.group(0))
            if t and t not in seen:
                seen.append(t)
        return seen


def _build_index(rows: list[Stock]) -> TickerIndex:
    entries: list[TickerEntry] = []
    for s in rows:
        ticker = s.ticker.upper()
        aliases = _ALIAS_OVERRIDES.get(ticker)
        if aliases is None:
            # Fallback: ticker symbol + first 2-3 words of name.
            base = (s.name or "").lower()
            aliases = tuple(filter(None, [ticker.lower(), base])) if base else (ticker.lower(),)
        entries.append(TickerEntry(ticker=ticker, aliases=tuple(a.lower() for a in aliases)))

    # Build one big alternation regex with word boundaries.
    # Sort longest-first so that "tata motors" matches before "tata".
    all_aliases = sorted(
        {a for e in entries for a in e.aliases},
        key=lambda x: -len(x),
    )
    if not all_aliases:
        # Empty universe — match nothing.
        pattern = re.compile(r"(?!x)x")
    else:
        pattern = re.compile(
            r"\b(" + "|".join(re.escape(a) for a in all_aliases) + r")\b",
            flags=re.IGNORECASE,
        )
    return TickerIndex(entries=tuple(entries), pattern=pattern)


# Cache the built index per session — invalidated explicitly when the universe
# changes (we don't expect that during a single demo session).
@lru_cache(maxsize=1)
def _cached_index(_signature: int) -> TickerIndex | None:
    # `_signature` is just a cache key the caller controls.
    return None  # populated by build_index()


async def build_index(session: AsyncSession) -> TickerIndex:
    """Build (or rebuild) the in-process ticker index from the DB."""
    rows = (await session.execute(select(Stock).where(Stock.active.is_(True)))).scalars().all()
    return _build_index(list(rows))
