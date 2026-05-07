"""Intent classification + ticker extraction.

A small, cheap GPT call before the main orchestrator. Buys us:
  1. A coarse routing label so the workhorse can pre-plan its tools.
  2. Cheap ticker extraction.

**Internal-tool mode** (Phase-2 default): the bot answers buy/sell/target/SL
questions with analyst views, so those stop being `refuse`. `refuse` is now
reserved for genuine off-topic / nonsense / non-financial queries.

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
    "technicals",     # "RSI on X" / "MACD signal" / "key levels"
    "holding",        # "promoter holding" / "who owns X" / "FII flow"
    "deals",          # "block deals on X" / "institutional flows"
    "research",       # "from X's annual report" / "what did mgmt say about Y"
    "advisory",       # "should I buy X" / "target for X" / "SL for X"
    "education",      # "what is P/E ratio"
    "refuse",         # off-topic / nonsense / non-financial only
    "other",
]


_INTENT_SYSTEM = """Classify a user message about Indian stocks. Output STRICT JSON:
  {"intent": "<one-of-below>", "ticker": "<UPPERCASE_NSE_SYMBOL>"|null}

Allowed intents and examples:

- "quote"        → live or last-traded price.
                   "price of reliance"          → quote, RELIANCE
                   "TCS price"                   → quote, TCS

- "news"         → recent headlines or "why is X moving today".
                   "why is tata motors falling"  → news, TATAMOTORS
                   "news on infy"                → news, INFY

- "company_info" → fundamentals: sector, market cap, P/E, ROE, P/B, 52w range.
                   "tell me about reliance"      → company_info, RELIANCE
                   "P/E of TCS"                  → company_info, TCS

- "technicals"   → RSI, MACD, Bollinger, SMA, EMA, ATR, support/resistance,
                   pivots, Fibonacci.
                   "RSI on Reliance"             → technicals, RELIANCE
                   "key levels for HDFC Bank"    → technicals, HDFCBANK
                   "is INFY oversold"            → technicals, INFY

- "holding"      → quarterly shareholding, promoter / FII / DII split, pledge.
                   "promoter holding for adani"  → holding, ADANIENT
                   "who owns infosys"            → holding, INFY

- "deals"        → bulk / block deals, institutional flows, named clients.
                   "block deals on reliance"     → deals, RELIANCE
                   "who's buying ICICI bank"     → deals, ICICIBANK

- "research"     → quote / cite the company's own annual report, concall
                   transcript, or any ingested research document.
                   "what did reliance management say about retail growth" → research, RELIANCE
                   "from TCS annual report, comments on AI"               → research, TCS
                   "INFY chairman's letter on margins"                     → research, INFY

- "advisory"     → buy / sell / hold opinion, price target, stop-loss, entry
                   level, F&O strategy, intraday view. **The bot answers these
                   with an analyst view** in internal-tool mode.
                   "should I buy reliance"       → advisory, RELIANCE
                   "target for adani"            → advisory, ADANIENT
                   "SL for HDFC bank"            → advisory, HDFCBANK
                   "intraday call for tcs"       → advisory, TCS

- "education"    → generic concept (no specific ticker).
                   "what is P/E ratio"           → education, null
                   "explain stop loss"           → education, null

- "refuse"       → genuinely off-topic / nonsense / non-financial.
                   "what's the weather in mumbai" → refuse, null
                   "asdfghjkl"                    → refuse, null
                   "tell me a joke"               → refuse, null

- "other"        → anything that doesn't fit above (greetings, multi-topic).

CRITICAL:
- Buy/sell/target/SL/intraday/F&O questions are "advisory", NOT "refuse".
- "refuse" is reserved for off-topic / nonsense only — NEVER for stock advice.
- A factual question (price / news / fundamentals / technicals / holdings) is
  always its specific intent, never "advisory" and never "refuse".
"""


_FORCE_JSON = {"type": "json_object"}

_VALID_INTENTS = {
    "quote", "news", "company_info", "technicals", "holding", "deals",
    "research", "advisory", "education", "refuse", "other",
}


async def classify(client: AsyncOpenAI, user_message: str) -> dict:
    """Best-effort classification. Returns {"intent": Intent, "ticker": str|None}.
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
        if intent not in _VALID_INTENTS:
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
