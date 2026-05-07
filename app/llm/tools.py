"""LLM tool catalog (OpenAI tool-calling shape) + dispatch.

Each tool corresponds 1:1 to a real backend service that already exists. Tool
results are JSON — never prose — so the verifier (D5) can match numeric claims
in the LLM's output against the source-truth set.
"""

from __future__ import annotations

import json
from typing import Any

from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

import pandas as pd
from sqlalchemy import desc, select

from datetime import date, timedelta

from app.analytics.levels import compute_levels
from app.data.info_service import get_info
from app.data.news_service import get_news_for_ticker
from app.data.quote_service import get_quote
from app.data.sources.nse_shareholding import quarter_label
from app.db.models.deal import Deal
from app.db.models.holding import Holding
from app.db.models.price import PriceDaily
from app.db.models.technicals import Technicals
from app.llm.auth import load_state
from app.llm.memory import memory_service


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_quote",
            "description": (
                "Get the current cross-validated price for one Indian stock "
                "(NSE/BSE). Returns the median price across yfinance, NSE, "
                "Screener, and Moneycontrol with a HIGH/MED/LOW confidence label "
                "based on inter-source spread. Use this whenever the user asks "
                "for a price, change, or day range."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "NSE ticker symbol (e.g., RELIANCE, TCS, HDFCBANK).",
                    },
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": (
                "Get recent headlines for an Indian stock with sentiment scores. "
                "Use this for 'why is X falling' or 'what's the news on X' questions. "
                "Sources are public RSS feeds (Pulse, Moneycontrol, ET Markets)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "NSE ticker symbol"},
                    "hours": {
                        "type": "integer",
                        "description": "Lookback window in hours (default 24, max 72).",
                        "minimum": 1,
                        "maximum": 72,
                    },
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_technicals",
            "description": (
                "Get the latest technical-indicator snapshot for an Indian stock: "
                "RSI-14, MACD(12,26,9), Bollinger(20,2), SMA-20/50/200, EMA-12/26, "
                "ATR-14, 20-day average volume. Computed nightly off our EOD "
                "bhavcopy ingest. Use this for questions about momentum, trend "
                "(price vs SMA-50/200), volatility (ATR / Bollinger width), or "
                "stop-loss observations (ATR is the standard input). Returns "
                "factual indicator values plus a small qualitative summary "
                "(rsi_zone, bb_position) — no recommendations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "NSE ticker symbol"},
                    "days": {
                        "type": "integer",
                        "description": "How many recent bars to include (default 1, max 60).",
                        "minimum": 1,
                        "maximum": 60,
                    },
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_levels",
            "description": (
                "Get observed price levels for an Indian stock: classic floor-trader "
                "pivots from yesterday's HLC (PP, R1-R3, S1-S3), multi-touch "
                "support/resistance bands clustered from the last ~90 trading days, "
                "and Fibonacci retracements from the most recent swing high/low. "
                "These are factual price points where buyers/sellers have repeatedly "
                "shown up — pure observation, not advice. Use for questions about "
                "key levels, support, resistance, or pivots."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "NSE ticker symbol"},
                    "window": {
                        "type": "integer",
                        "description": "Lookback bars for S/R clustering (default 90, max 365).",
                        "minimum": 10,
                        "maximum": 365,
                    },
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_holding",
            "description": (
                "Get the quarterly NSE shareholding pattern for an Indian stock — "
                "promoter & promoter-group %, public %, employee-trust %, plus "
                "QoQ and YoY deltas. Use this for questions about promoter holding "
                "changes, FII / DII movement, or any 'who owns this' query. "
                "Returns the latest N quarters with computed deltas; flags "
                "promoter shifts of ≥1pp as 'significant'. Pure factual data, "
                "no recommendations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "NSE ticker symbol"},
                    "quarters": {
                        "type": "integer",
                        "description": "How many recent quarters to include (default 8, max 40).",
                        "minimum": 1,
                        "maximum": 40,
                    },
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_deals",
            "description": (
                "Get bulk and block deals for an Indian stock — large single "
                "transactions reported by NSE (bulk: ≥0.5%% of equity; block: "
                "negotiated cross-trades ≥₹10cr). Returns recent deals with "
                "client name, side (BUY/SELL), quantity, price, and a summary "
                "of net activity (buys vs sells). Useful for 'who is buying/"
                "selling' questions and tracking institutional flows. Pure "
                "factual data, no recommendations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "NSE ticker symbol"},
                    "kind": {
                        "type": "string",
                        "enum": ["bulk", "block", "any"],
                        "description": "deal type filter (default any)",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Lookback window (default 90, max 365).",
                        "minimum": 1,
                        "maximum": 365,
                    },
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_research",
            "description": (
                "Semantic search over ingested annual reports / research documents "
                "for an Indian stock. Use this for 'what did management say about X' "
                "questions or any qualitative ask grounded in the company's own "
                "filings. Returns the top-K most-relevant chunks with the document "
                "title, FY tag, page number, and a similarity score. The chunks "
                "are factual extracts from the source PDF — quote them directly "
                "and cite (title, page #) in the answer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "NSE ticker symbol"},
                    "query": {
                        "type": "string",
                        "description": "the question to retrieve evidence for, e.g. 'Reliance JIO retail growth strategy'",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "How many chunks to return (default 5, max 20).",
                        "minimum": 1,
                        "maximum": 20,
                    },
                },
                "required": ["ticker", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_company_info",
            "description": (
                "Get fundamental info about an Indian stock: sector, industry, market "
                "cap, P/E (trailing + forward), price-to-book, dividend yield, beta, "
                "52-week range. Pulled from yfinance and Screener.in side-by-side."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "NSE ticker symbol"},
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_screener",
            "description": (
                "Run a stock screener across the NIFTY-100 universe. Accept either "
                "a saved screener name (e.g. 'oversold_quality', 'value_rebound', "
                "'momentum_breakout') or a custom filter expression using the DSL "
                "(e.g. 'rsi_14 < 30 AND pe_trailing < 20 AND promoter_pct > 50'). "
                "Returns matching tickers ranked by score. Use for questions like "
                "'screen for oversold quality stocks' or 'RSI < 30 with good PE'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "A saved screener name (e.g. 'oversold_quality', 'value_rebound', 'momentum_breakout', 'high_pledge_avoid', 'fii_buying', 'promoter_increasing').",
                    },
                    "expr": {
                        "type": "string",
                        "description": "A custom filter expression in the screener DSL (e.g. 'rsi_14 < 30 AND pe_trailing < 20').",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max tickers to return (default 10, max 50).",
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyse_portfolio",
            "description": (
                "Analyse a user's imported portfolio — returns concentration risk, "
                "sector exposure breakdown, top-5 position weight, blended beta, "
                "dividend yield, and 1-year drawdown. Requires a portfolio_id from "
                "a prior import. Use for 'analyse my portfolio' or 'portfolio "
                "diagnostics' questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "portfolio_id": {
                        "type": "integer",
                        "description": "The portfolio ID returned from a prior import.",
                    },
                },
                "required": ["portfolio_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_ideas",
            "description": (
                "Generate ranked trade ideas by combining screener output, technicals, "
                "and shareholding data. Returns a list of candidates with ticker, "
                "thesis, observed entry level, ATR-based stop-loss, technical target "
                "range, and a composite score. All numbers come from tool results — "
                "nothing is fabricated. Use for 'give me trade ideas' or 'what should "
                "I look at today'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "risk_profile": {
                        "type": "string",
                        "enum": ["conservative", "balanced", "aggressive"],
                        "description": "The user's risk profile — filters and ranks ideas accordingly.",
                    },
                    "theme": {
                        "type": "string",
                        "description": "Optional theme to narrow ideas (e.g. 'value rebound', 'momentum breakout').",
                    },
                },
                "required": ["risk_profile"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "backtest_screener",
            "description": (
                "Backtest a saved screener over a historical period. Replays the "
                "screener daily on past data and returns hit rate, mean return per "
                "signal, worst drawdown, number of signals, and an equity curve. "
                "Use for 'backtest the oversold_quality screener' or 'how did "
                "value_rebound perform last year'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The saved screener name to backtest.",
                    },
                    "period_days": {
                        "type": "integer",
                        "description": "Lookback period in days (default 365, max 365).",
                        "minimum": 30,
                        "maximum": 365,
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_watchlist",
            "description": (
                "Add a ticker to the signed-in user's persistent watchlist. "
                "Returns the updated watchlist size. Use when the user says "
                "'add X to my watchlist' or 'watch X for me'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "NSE ticker symbol to add (e.g. RELIANCE, TCS).",
                    },
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_fact",
            "description": (
                "Persist a durable personalization fact about the signed-in user. "
                "Use only for stable preferences such as sectors they track, "
                "watchlists, risk tolerance, holding horizon, or preferred analyst "
                "style. Do not store transient ticker mentions, tool data, prices, "
                "news, greetings, or anything from a refusal."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "A short first-person durable fact, e.g. 'User prefers dividend payers'.",
                    },
                },
                "required": ["fact"],
            },
        },
    },
]


async def dispatch(
    name: str,
    args: dict[str, Any],
    *,
    session: AsyncSession,
    redis: aioredis.Redis,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Run one tool by name. Always returns a JSON-serialisable dict."""
    if name == "get_quote":
        return await get_quote(str(args["ticker"]), redis, session)
    if name == "get_news":
        hours = int(args.get("hours") or 24)
        return await get_news_for_ticker(session, redis, str(args["ticker"]), hours=hours)
    if name == "get_company_info":
        return await get_info(session, str(args["ticker"]))
    if name == "get_technicals":
        return await _get_technicals_payload(
            session, str(args["ticker"]), days=int(args.get("days") or 1)
        )
    if name == "get_levels":
        return await _get_levels_payload(
            session, str(args["ticker"]), window=int(args.get("window") or 90)
        )
    if name == "get_holding":
        return await _get_holding_payload(
            session,
            redis,
            str(args["ticker"]),
            quarters=int(args.get("quarters") or 8),
        )
    if name == "get_deals":
        return await _get_deals_payload(
            session,
            str(args["ticker"]),
            kind=str(args.get("kind") or "any"),
            days=int(args.get("days") or 90),
        )
    if name == "get_research":
        return await _get_research_payload(
            session, redis,
            ticker=str(args["ticker"]),
            query=str(args["query"]),
            top_k=int(args.get("top_k") or 5),
        )
    if name == "run_screener":
        return await _run_screener_payload(
            session,
            name=args.get("name"),
            expr=args.get("expr"),
            limit=int(args.get("limit") or 10),
            risk_profile=args.get("_risk_profile"),
        )
    if name == "analyse_portfolio":
        return await _analyse_portfolio_payload(
            session,
            portfolio_id=int(args["portfolio_id"]),
        )
    if name == "propose_ideas":
        return await _propose_ideas_payload(
            session,
            redis,
            risk_profile=str(args["risk_profile"]),
            theme=args.get("theme"),
        )
    if name == "backtest_screener":
        return await _backtest_screener_payload(
            session,
            name=str(args["name"]),
            period_days=int(args.get("period_days") or 365),
        )
    if name == "add_to_watchlist":
        return await _add_to_watchlist_payload(
            session,
            ticker=str(args["ticker"]),
            user_id=user_id,
        )
    if name == "remember_fact":
        fact = str(args.get("fact") or "").strip()
        if not user_id:
            return {"stored": False, "error": "memory requires a signed-in user"}
        if not fact:
            return {"stored": False, "error": "fact is required"}
        auth = await load_state(redis)
        saved = await memory_service.add_explicit(
            user_id,
            fact,
            api_key=auth.api_key if auth.configured else None,
            redis=redis,
        )
        if saved is None:
            return {"stored": False, "fact": fact, "error": "memory save failed"}
        return {"stored": True, "fact": fact}
    return {"error": f"unknown tool: {name}"}


async def _get_research_payload(
    session: AsyncSession,
    redis,
    *,
    ticker: str,
    query: str,
    top_k: int,
) -> dict[str, Any]:
    """Embed the query, run similarity search via the configured backend,
    return the top-K chunks."""
    from app.rag.embeddings import embed_one
    from app.rag.retrieval import to_dict
    from app.rag.vector_store import get_store

    sym = ticker.upper().strip()
    try:
        q_emb = await embed_one(query, redis=redis)
    except Exception as e:  # noqa: BLE001
        return {"ticker": sym, "available": False, "error": f"embed: {e!s}"}

    store = get_store()
    hits = await store.search(
        session, ticker=sym, query_embedding=q_emb,
        top_k=max(1, min(top_k, 20)), kinds=None,
    )
    if not hits:
        return {
            "ticker": sym,
            "available": False,
            "query": query,
            "n_hits": 0,
            "note": (
                "No ingested research documents for this ticker. Ask "
                "the operator to run `scripts.ingest_research` for it."
            ),
        }
    return {
        "ticker": sym,
        "available": True,
        "query": query,
        "n_hits": len(hits),
        "hits": [to_dict(h) for h in hits],
    }


async def _get_deals_payload(
    session: AsyncSession, ticker: str, *, kind: str, days: int
) -> dict[str, Any]:
    sym = ticker.upper().strip()
    cutoff = date.today() - timedelta(days=max(1, min(days, 365)))
    stmt = (
        select(Deal)
        .where(Deal.symbol == sym)
        .where(Deal.trade_date >= cutoff)
        .order_by(desc(Deal.trade_date), desc(Deal.id))
        .limit(50)
    )
    if kind in ("bulk", "block"):
        stmt = stmt.where(Deal.kind == kind)
    rows = (await session.execute(stmt)).scalars().all()

    if not rows:
        return {"ticker": sym, "available": False, "n_deals": 0, "kind": kind, "lookback_days": days}

    from decimal import Decimal as D
    buy_qty = sum(r.quantity for r in rows if r.side == "BUY")
    sell_qty = sum(r.quantity for r in rows if r.side == "SELL")
    items = [
        {
            "trade_date": r.trade_date.isoformat(),
            "client_name": r.client_name,
            "side": r.side,
            "quantity": r.quantity,
            "avg_price": str(r.avg_price),
            "trade_value_inr": str((r.avg_price * r.quantity).quantize(D("0.01"))),
            "kind": r.kind,
        }
        for r in rows
    ]
    return {
        "ticker": sym,
        "available": True,
        "kind": kind,
        "lookback_days": days,
        "n_deals": len(items),
        "n_buys": sum(1 for r in rows if r.side == "BUY"),
        "n_sells": sum(1 for r in rows if r.side == "SELL"),
        "buy_qty": buy_qty,
        "sell_qty": sell_qty,
        "net_qty": buy_qty - sell_qty,
        "items": items,
    }


async def _get_holding_payload(
    session: AsyncSession, redis, ticker: str, *, quarters: int
) -> dict[str, Any]:
    sym = ticker.upper().strip()
    rows = (
        await session.execute(
            select(Holding)
            .where(Holding.ticker == sym)
            .order_by(desc(Holding.quarter_end))
            .limit(max(1, min(quarters, 40)))
        )
    ).scalars().all()
    if not rows:
        return {"ticker": sym, "available": False, "note": "no shareholding rows"}

    def _f(d):
        return str(d) if d is not None else None

    series = [
        {
            "quarter_end": r.quarter_end.isoformat(),
            "quarter_label": quarter_label(r.quarter_end),
            "promoter_pct": _f(r.promoter_pct),
            "public_pct": _f(r.public_pct),
            "employee_trust_pct": _f(r.employee_trust_pct),
        }
        for r in rows
    ]
    latest = rows[0]
    payload = {
        "ticker": sym,
        "available": True,
        "as_of": latest.quarter_end.isoformat(),
        "latest_quarter_label": quarter_label(latest.quarter_end),
        "latest": {
            "promoter_pct": _f(latest.promoter_pct),
            "public_pct": _f(latest.public_pct),
            "employee_trust_pct": _f(latest.employee_trust_pct),
        },
        "series": series,
    }

    # Best-effort pledge drill-down. Failures are silent — pledge data is
    # additive, not load-bearing for the holding answer.
    pledge = await _fetch_pledge_cached(redis, sym)
    if pledge is not None:
        payload["pledge"] = pledge
        payload["latest"]["pledged_pct"] = pledge.get("pledged_pct")
        payload["latest"]["pledge_risk_band"] = pledge.get("risk_band")
    if getattr(latest, "xbrl_url", None):
        payload["xbrl_url"] = latest.xbrl_url

    return payload


_PLEDGE_TTL_S = 6 * 3600  # 6h: pledge filings are quarterly + ad-hoc — no need to hammer NSE


async def _fetch_pledge_cached(redis, ticker: str) -> dict[str, Any] | None:
    """Return the latest pledge row as a small JSON-serialisable dict, or
    None if NSE blocked / returned nothing. Cached in Redis so chat turns
    never trigger a fresh scrape.
    """
    import json as _json

    from app.data.sources.nse_pledge import fetch as fetch_pledge

    sym = ticker.upper().strip()
    cache_key = f"pledge:{sym}"

    if redis is not None:
        try:
            cached = await redis.get(cache_key)
        except Exception:  # noqa: BLE001
            cached = None
        if cached:
            try:
                return _json.loads(cached)
            except Exception:  # noqa: BLE001
                pass

    try:
        rows = await fetch_pledge(sym)
    except Exception as e:  # noqa: BLE001
        # Cache a negative for a short window so we don't hammer NSE on
        # repeated fetches when it's blocking us.
        if redis is not None:
            try:
                await redis.set(cache_key, _json.dumps(None), ex=300)
            except Exception:  # noqa: BLE001
                pass
        # Returning None upstream — caller treats as "pledge unavailable".
        _ = e  # explicit drop; logged at scrape level if needed
        return None

    if not rows:
        return None

    latest = rows[0]
    out = {
        "as_of": latest.quarter_end.isoformat(),
        "as_of_label": quarter_label(latest.quarter_end),
        "pledged_pct": str(latest.pledged_pct) if latest.pledged_pct is not None else None,
        "promoter_pct": str(latest.promoter_pct) if latest.promoter_pct is not None else None,
        "num_shares_pledged": latest.num_shares_pledged,
        "total_promoter_shares": latest.total_promoter_shares,
        "total_issued_shares": latest.total_issued_shares,
        "broadcast_at": latest.broadcast_at.isoformat() if latest.broadcast_at else None,
        "risk_band": latest.risk_band,
    }
    if redis is not None:
        try:
            await redis.set(cache_key, _json.dumps(out), ex=_PLEDGE_TTL_S)
        except Exception:  # noqa: BLE001
            pass
    return out


async def _get_levels_payload(
    session: AsyncSession, ticker: str, *, window: int
) -> dict[str, Any]:
    sym = ticker.upper().strip()
    rows = (
        await session.execute(
            select(
                PriceDaily.ts,
                PriceDaily.open,
                PriceDaily.high,
                PriceDaily.low,
                PriceDaily.close,
                PriceDaily.volume,
            )
            .where(PriceDaily.ticker == sym)
            .where(PriceDaily.source == "nsearchives")
            .order_by(desc(PriceDaily.ts))
            .limit(max(10, min(window, 365)))
        )
    ).all()
    if not rows:
        return {"ticker": sym, "available": False, "note": "no prices for ticker"}

    df = pd.DataFrame(
        rows, columns=["ts", "open", "high", "low", "close", "volume"]
    ).sort_values("ts").set_index("ts")
    out = compute_levels(df, window=window)
    out["ticker"] = sym
    return out


async def _get_technicals_payload(
    session: AsyncSession, ticker: str, *, days: int
) -> dict[str, Any]:
    """Read the most recent indicator rows; mirror /technicals/{ticker} shape."""
    sym = ticker.upper().strip()
    rows = (
        await session.execute(
            select(Technicals)
            .where(Technicals.ticker == sym)
            .order_by(desc(Technicals.ts))
            .limit(max(1, min(days, 60)))
        )
    ).scalars().all()
    if not rows:
        return {"ticker": sym, "available": False, "note": "no technicals computed yet"}

    def _f(d):
        return str(d) if d is not None else None

    latest = rows[0]
    series = [
        {
            "ts": r.ts.isoformat() if r.ts else None,
            "close": _f(r.close),
            "rsi_14": _f(r.rsi_14),
            "macd": _f(r.macd),
            "macd_signal": _f(r.macd_signal),
            "sma_50": _f(r.sma_50),
            "sma_200": _f(r.sma_200),
            "atr_14": _f(r.atr_14),
        }
        for r in rows
    ]
    summary: dict[str, Any] = {"available": True}
    if latest.rsi_14 is not None:
        v = float(latest.rsi_14)
        summary["rsi_zone"] = (
            "overbought" if v >= 70 else "oversold" if v <= 30 else "neutral"
        )
    if latest.close is not None and latest.sma_50 is not None:
        summary["above_sma50"] = float(latest.close) > float(latest.sma_50)
    if latest.close is not None and latest.sma_200 is not None:
        summary["above_sma200"] = float(latest.close) > float(latest.sma_200)
    if latest.macd is not None and latest.macd_signal is not None:
        summary["macd_above_signal"] = float(latest.macd) > float(latest.macd_signal)

    return {
        "ticker": sym,
        "as_of": latest.ts.isoformat() if latest.ts else None,
        "summary": summary,
        "latest": {
            "close": _f(latest.close),
            "rsi_14": _f(latest.rsi_14),
            "macd": _f(latest.macd),
            "macd_signal": _f(latest.macd_signal),
            "macd_hist": _f(latest.macd_hist),
            "bb_upper": _f(latest.bb_upper),
            "bb_middle": _f(latest.bb_middle),
            "bb_lower": _f(latest.bb_lower),
            "sma_20": _f(latest.sma_20),
            "sma_50": _f(latest.sma_50),
            "sma_200": _f(latest.sma_200),
            "ema_12": _f(latest.ema_12),
            "ema_26": _f(latest.ema_26),
            "atr_14": _f(latest.atr_14),
            "vol_avg_20": latest.vol_avg_20,
        },
        "series": series,
    }


RISK_PROFILE_SCREENER_GUARDS: dict[str, str] = {
    "conservative": "promoter_pct > 50 AND pe_trailing < 25",
    "balanced": "",
    "aggressive": "",
}


async def _run_screener_payload(
    session: AsyncSession,
    *,
    name: str | None,
    expr: str | None,
    limit: int,
    risk_profile: str | None = None,
) -> dict[str, Any]:
    """Run a screener by name or expression. Calls Dev A's screener engine."""
    if not name and not expr:
        return {"available": False, "error": "provide either 'name' (saved screener) or 'expr' (filter expression)"}
    limit = max(1, min(limit, 50))
    try:
        from app.analytics.screener import evaluate_expression, get_saved_screener
        if name and not expr:
            saved = await get_saved_screener(session, name)
            if saved is None:
                return {"available": False, "error": f"no saved screener named '{name}'"}
            expr = saved.expr
        expr = _apply_risk_guard(expr, risk_profile)
        results = await evaluate_expression(session, expr, limit=limit)
        return {
            "available": True,
            "expr": expr,
            "screener_name": name,
            "risk_profile_applied": risk_profile,
            "tickers": results.tickers,
            "universe_size": results.universe_size,
            "exec_ms": results.exec_ms,
        }
    except ImportError:
        return {
            "available": False,
            "error": "screener engine not yet deployed — coming in the data-engine track",
        }
    except Exception as e:  # noqa: BLE001
        return {"available": False, "error": f"screener error: {e!s}"}


def _apply_risk_guard(expr: str, risk_profile: str | None) -> str:
    """Append profile-specific safety filters to a screener expression."""
    if not risk_profile or not expr:
        return expr or ""
    guard = RISK_PROFILE_SCREENER_GUARDS.get(risk_profile, "")
    if not guard:
        return expr
    return f"({expr}) AND {guard}"


async def _analyse_portfolio_payload(
    session: AsyncSession,
    *,
    portfolio_id: int,
) -> dict[str, Any]:
    """Analyse a user portfolio. Calls Dev A's portfolio diagnostics."""
    try:
        from app.analytics.portfolio import get_diagnostics
        diag = await get_diagnostics(session, portfolio_id)
        if diag is None:
            return {"available": False, "error": f"portfolio {portfolio_id} not found"}
        return {
            "available": True,
            "portfolio_id": portfolio_id,
            "concentration": diag.concentration,
            "sector_pct": diag.sector_pct,
            "top_5_pct": diag.top_5_pct,
            "beta_blend": diag.beta_blend,
            "div_yield": diag.div_yield,
            "drawdown_1y": diag.drawdown_1y,
        }
    except ImportError:
        return {
            "available": False,
            "error": "portfolio analytics not yet deployed — coming in the data-engine track",
        }
    except Exception as e:  # noqa: BLE001
        return {"available": False, "error": f"portfolio error: {e!s}"}


async def _propose_ideas_payload(
    session: AsyncSession,
    redis: aioredis.Redis,
    *,
    risk_profile: str,
    theme: str | None,
) -> dict[str, Any]:
    """Generate ranked trade ideas. Full implementation in B-3; stub for B-1."""
    if risk_profile not in ("conservative", "balanced", "aggressive"):
        return {"available": False, "error": f"invalid risk_profile: {risk_profile}"}
    try:
        from app.analytics.screener import evaluate_expression, get_saved_screener
        screener_name = _theme_to_screener(theme, risk_profile)
        saved = await get_saved_screener(session, screener_name)
        if saved is None:
            return {
                "available": False,
                "error": f"no screener for theme '{theme or 'default'}' and profile '{risk_profile}'",
            }
        results = await evaluate_expression(session, saved.expr, limit=5)
        ideas = []
        for t in results.tickers:
            ideas.append({
                "ticker": t["symbol"],
                "thesis": t.get("thesis", "Matches screener criteria"),
                "score": t.get("score"),
            })
        return {
            "available": True,
            "risk_profile": risk_profile,
            "theme": theme,
            "screener_used": screener_name,
            "ideas": ideas,
        }
    except ImportError:
        return {
            "available": False,
            "error": "trade-idea engine not yet deployed — coming in the data-engine track",
        }
    except Exception as e:  # noqa: BLE001
        return {"available": False, "error": f"idea engine error: {e!s}"}


def _theme_to_screener(theme: str | None, risk_profile: str) -> str:
    """Map a user theme + risk profile to a saved screener name."""
    if theme:
        normalized = theme.lower().replace(" ", "_").replace("-", "_")
        for known in ("oversold_quality", "value_rebound", "momentum_breakout",
                       "high_pledge_avoid", "fii_buying", "promoter_increasing"):
            if normalized in known or known in normalized:
                return known
    defaults = {
        "conservative": "oversold_quality",
        "balanced": "value_rebound",
        "aggressive": "momentum_breakout",
    }
    return defaults.get(risk_profile, "value_rebound")


async def _backtest_screener_payload(
    session: AsyncSession,
    *,
    name: str,
    period_days: int,
) -> dict[str, Any]:
    """Backtest a saved screener. Calls Dev A's backtest engine."""
    period_days = max(30, min(period_days, 365))
    try:
        from app.analytics.backtest import run_backtest
        result = await run_backtest(session, screener_name=name, period_days=period_days)
        if result is None:
            return {"available": False, "error": f"no saved screener named '{name}'"}
        return {
            "available": True,
            "screener_name": name,
            "period_days": period_days,
            "hit_rate": result.hit_rate,
            "mean_return": result.mean_return,
            "worst_drawdown": result.worst_drawdown,
            "n_signals": result.n_signals,
        }
    except ImportError:
        return {
            "available": False,
            "error": "backtest engine not yet deployed — coming in the data-engine track",
        }
    except Exception as e:  # noqa: BLE001
        return {"available": False, "error": f"backtest error: {e!s}"}


async def _add_to_watchlist_payload(
    session: AsyncSession,
    *,
    ticker: str,
    user_id: str | None,
) -> dict[str, Any]:
    """Add a ticker to the user's watchlist."""
    sym = ticker.upper().strip()
    if not user_id:
        return {"ok": False, "error": "watchlist requires a signed-in user"}
    try:
        from app.db.models.watchlist import Watchlist
        from sqlalchemy import func, select as sa_select

        existing = (
            await session.execute(
                sa_select(Watchlist).where(
                    Watchlist.user_id == user_id,
                    Watchlist.ticker == sym,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(Watchlist(user_id=user_id, ticker=sym))
            await session.commit()
        count = (
            await session.execute(
                sa_select(func.count()).select_from(Watchlist).where(
                    Watchlist.user_id == user_id,
                )
            )
        ).scalar() or 0
        return {"ok": True, "ticker": sym, "watchlist_size": count}
    except ImportError:
        return {
            "ok": False,
            "error": "watchlist table not yet deployed — coming in the data-engine track",
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"watchlist error: {e!s}"}


def tool_result_to_json_string(payload: dict[str, Any]) -> str:
    """Compact JSON string that we send back as the `tool` message content."""
    return json.dumps(payload, default=str, ensure_ascii=False)
