"""Intent classification + ticker extraction.

A small, cheap GPT call that runs *before* the main orchestrator. It buys us:
  1. A coarse routing label so we can short-circuit pure refusals (no need to
     burn the workhorse on "Should I buy Reliance?").
  2. Cheap ticker extraction — many user queries name a single ticker; pulling
     it out here lets the orchestrator pre-warm the relevant tool.

Returns a small structured dict; never raises (degrades to {intent: "other"}).
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

Intent = Literal[
    "quote",          # "price of X"
    "news",           # "what's the news on X" / "why is X falling"
    "company_info",   # "tell me about X" / "what is X's P/E"
    "education",      # "what is P/E ratio"
    "refuse",         # "should I buy X" / "target for X"
    "other",
]


_INTENT_SYSTEM = """Classify a user message about Indian stocks. Output STRICT JSON:
  {"intent": "quote"|"news"|"company_info"|"education"|"refuse"|"other", "ticker": "<UPPERCASE_NSE_SYMBOL>"|null}

Definitions and examples:

- "quote"        → user wants the current/last price, change %, day range.
                   "price of reliance"           → quote, RELIANCE
                   "what is HDFCBANK trading at"  → quote, HDFCBANK
                   "TCS price"                    → quote, TCS

- "news"         → user wants recent headlines, or asks WHY a stock moved.
                   "why is tata motors falling"   → news, TATAMOTORS
                   "news on infy"                 → news, INFY
                   "any updates on adani"         → news, ADANIENT

- "company_info" → user wants fundamentals: sector, industry, P/E, ROE, market cap, 52w range.
                   "tell me about reliance"       → company_info, RELIANCE
                   "what does TCS do"             → company_info, TCS
                   "infy market cap and pe"       → company_info, INFY

- "education"    → user wants a generic concept explained (no stock-specific advice).
                   "what is P/E ratio"            → education, null
                   "explain stop loss"            → education, null

- "refuse"       → user is asking for ADVICE / a RECOMMENDATION / a TARGET / a TRADE.
                   ONLY use refuse for these patterns:
                     "should I buy X" / "is X a good buy" / "should I sell X"
                     "what's the target for X"
                     "where to set stop loss for X"
                     "X intraday strategy" / "X for swing trade"
                     "options strategy on X" / "puts/calls on X"
                   "should i buy reliance"        → refuse, RELIANCE
                   "target for adani"             → refuse, ADANIENT
                   "options on bank nifty"        → refuse, null

- "other"        → none of the above (greeting, off-topic, unclear).

CRITICAL: A pure factual question about a price, news, or fundamentals is NEVER "refuse".
Refuse only when the user is asking what to DO or for a target/SL.
"""


_FORCE_JSON = {"type": "json_object"}


async def classify(client: AsyncOpenAI, user_message: str) -> dict:
    """Best-effort classification. Returns:
       {"intent": Intent, "ticker": str|None}.
    Never raises.
    """
    settings = get_settings()

    try:
        resp = await client.chat.completions.create(
            model=settings.openai_model_router,
            temperature=0,
            max_tokens=60,
            response_format=_FORCE_JSON,
            messages=[
                {"role": "system", "content": _INTENT_SYSTEM},
                {"role": "user", "content": user_message[:1000]},
            ],
        )
        content = (resp.choices[0].message.content or "").strip()
        data = json.loads(content)
        intent = str(data.get("intent") or "other").lower()
        if intent not in {"quote", "news", "company_info", "education", "refuse", "other"}:
            intent = "other"
        ticker_raw = data.get("ticker")
        ticker = (
            str(ticker_raw).upper().strip()
            if isinstance(ticker_raw, str) and ticker_raw.strip()
            else None
        )
        return {"intent": intent, "ticker": ticker}
    except Exception as e:  # noqa: BLE001
        logger.warning("intent classify failed: %s", e)
        return {"intent": "other", "ticker": None}
