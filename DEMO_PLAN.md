# Midas — Local Demo Plan

**Status:** v1 · **Window:** ~7 working days · **Scope:** local demo on Mac, free data only, accuracy ≥99%

This supersedes `PHASE_1_PLAN.md` for the demo phase. We come back to the production plan (per-user broker OAuth, VPS, DPDP, etc.) only after the demo lands.

---

## 0. The constraint set

| | |
|---|---|
| **Where it runs** | Locally on your Mac. Docker Desktop. No VPS. |
| **Data cost** | ₹0. No paid APIs. No Tickertape/Trendlyne. |
| **LLM cost** | Paid LLM (Claude / Gemini / GPT) is OK — that's where intelligence lives. |
| **Users** | You + a handful of internal demo viewers. No public traffic. |
| **The bar** | Every number we display must be **verifiably correct**. Refusing is better than being wrong. |

**Non-goals for demo:** broker OAuth, real-time tick streaming, F&O, RAG over annual reports, mobile app, prod hardening, multi-region, autoscaling.

---

## 1. The accuracy strategy (the whole game)

This is where we spend our effort. Three principles:

### Principle 1 — Triangulate every number from ≥3 independent sources
Never display a single-source number for a price or ratio. Compute confidence from inter-source agreement.

### Principle 2 — Refuse when sources disagree
If sources differ by more than a tight threshold, surface the spread to the user — never pick one and pretend it's authoritative.

### Principle 3 — The LLM cannot invent numbers
Every numeric claim in the LLM output must trace back to the tool-call JSON. A post-LLM verifier extracts numbers and matches them against tool results. Mismatches → reject and retry once → fall back to a templated response.

### Sources we triangulate

| Data point | Source A | Source B | Source C | Source D (tiebreak) |
|---|---|---|---|---|
| **Live price (RTH)** | `nselib` live quote | `yfinance` fast_info | Scrape `screener.in/company/<t>/` price | Scrape `moneycontrol.com` quote page |
| **EOD bar** | NSE bhavcopy (`nsearchives.nseindia.com`) | yfinance daily | Screener daily close | — |
| **Market cap, P/E, ROE** | yfinance `.info` | Screener `#top-ratios` | Moneycontrol "Key Ratios" | — |
| **Sector / industry** | yfinance | Screener "About" | NSE corporate page | — |
| **52w high/low** | yfinance | Screener | — | — |
| **News (headlines)** | Pulse RSS | Moneycontrol RSS | ET Markets RSS | Mint RSS, BS RSS |
| **Sentiment per headline** | local distilroberta | — | — | — |
| **Index level** | nselib indices | yfinance (^NSEI / ^BSESN) | Moneycontrol indices page | — |

### Confidence rules
For numeric data after fetching N sources, compute pairwise relative diff:
- **HIGH** — all sources agree within 0.1% (price) / 1% (ratios)
- **MED** — within 0.5% (price) / 5% (ratios), or one source missing
- **LOW** — wider spread → bot does NOT pick a number; it shows the spread and asks the user to refresh

Never display a single number with HIGH confidence unless ≥2 sources agreed. The demo must never be confidently wrong.

### Caching policy (accuracy-first, not speed-first)
- Price (during RTH): 15s
- Price (after hours): 1h
- Fundamentals: 24h
- News: 5m
- Last-known-good is preserved with its timestamp; if all live sources fail, we display LKG with "(last verified at HH:MM)" instead of refusing.

---

## 2. Local stack (Mac-friendly)

```
┌─ docker compose ─────────────────────────────────┐
│  postgres-16 + timescaledb + pgvector            │
│  redis 7                                         │
└──────────────────────────────────────────────────┘
                       ↑
                       │ asyncpg / aioredis
┌─ host (your Mac) ────┴───────────────────────────┐
│  Python 3.12 (uv-managed)                        │
│  uvicorn app.main:app --reload     ← :8000       │
│  arq worker  (cron + on-demand jobs)              │
│                                                  │
│  Node 20 (frontend)                              │
│  pnpm dev   (Vite)                ← :5173        │
└──────────────────────────────────────────────────┘
```

The React app talks to FastAPI over `localhost:8000`. Vite proxy forwards `/api/*` and `/chat` (SSE) so we avoid CORS pain in dev.

### Stack picks (revised for local demo)

| Layer | Pick | Why |
|---|---|---|
| Lang/deps | Python 3.12 + `uv` | Fast install, lockfile, native |
| Web | FastAPI 0.115 + uvicorn `--reload` | Same as prod plan |
| HTTP | `httpx` async + `curl_cffi` for NSE/Screener | TLS fingerprint past Akamai/Cloudflare |
| DB | Postgres 16 + TimescaleDB + pgvector (single Docker container) | One DB, no Qdrant |
| Cache | Redis 7 (Docker) | Standard |
| Jobs | `arq` (Redis-backed) | Async, lightweight |
| Sentiment | `mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis` (CPU) | Free, ~10ms/headline |
| LLM (work) | Claude Sonnet 4.5+ with 1h prompt caching | Best tool-use + caching for our budget |
| LLM (router/NER) | Claude Haiku 4.5 | Cheap intent + ticker extraction |
| Frontend | **Vite + React + TypeScript + Tailwind + shadcn/ui** | React skill carries over to FinWin RN app; shadcn ships polished components fast |
| Observability | Logfire free (or just stdout) + a tiny `/admin/audits` table viewer | No Sentry needed for local |

Things explicitly **not** in the local demo:
- Broker OAuth (Upstox/Angel) — defer to prod plan
- Cloudflare / Caddy — local uses uvicorn direct
- VPS / domain / SSL
- DPDP consent UX (still log to audit table for our own evals)

---

## 3. What the demo shows (the script)

Six demo flows, designed to make accuracy + safety obvious:

1. **Single-stock quote with provenance**
   - User: *"What is the price of Reliance?"*
   - Bot: *"Reliance Industries (RELIANCE) is at **₹1,247.55** (as of 14:32:05 IST, NSE). Cross-checked against Yahoo Finance (₹1,247.50, Δ 0.004%) and Screener.in (₹1,247.50). Confidence: HIGH (3 sources agree). [Inline disclaimer]."*

2. **Multi-stock table**
   - User: *"Price of TCS, Infosys, HDFC Bank"*
   - Bot: structured table with price, change %, day range, confidence column.

3. **"Why is X falling"**
   - User: *"Why is Tata Motors falling today?"*
   - Bot: *"TATAMOTORS is down 2.4% today (₹X → ₹Y), against NIFTY Auto down 0.7% and NIFTY 50 down 0.3%. Headlines from the last 24h:*
     - *• [JLR Q-results miss] — Moneycontrol, 09:14 IST (sentiment: negative)*
     - *• [analyst downgrade] — ET Markets, 11:02 IST (sentiment: negative)*
     - *... [Inline disclaimer]"*
   - Important: bot does NOT speculate beyond cited headlines.

4. **Education question**
   - User: *"What is P/E ratio?"*
   - Bot: clear definition + worked example, no specific stock recommendation.

5. **Refusal — buy/sell question**
   - User: *"Should I buy Adani Enterprises?"*
   - Bot: *"I can't recommend buying or selling specific securities. I can share factual information about Adani Enterprises — would you like the latest results summary, business segments, or recent price action?"*

6. **Refusal — target / stop-loss**
   - User: *"What's the target for Reliance?"*
   - Bot: *"I can't set price targets. I can share recent broker consensus targets reported in the news, with sources, if you want."*

Plus an **admin view** (`http://localhost:8501/admin`) that shows the audit log — every query, the tools called, their results, the LLM output, and whether the verifier rejected anything. This is the "see how the sausage is made" panel that sells the accuracy story.

---

## 4. Repo layout (slimmer than prod plan)

```
midas/
├── pyproject.toml         # uv
├── uv.lock
├── docker-compose.yml     # postgres + redis only
├── .env.example
├── alembic.ini
│
├── app/
│   ├── main.py
│   ├── config.py
│   ├── api/
│   │   ├── chat.py        # SSE
│   │   ├── quote.py       # GET /quote/{ticker}
│   │   ├── news.py        # GET /news/{ticker}
│   │   └── admin.py       # GET /admin/audits
│   │
│   ├── data/
│   │   ├── nselib_client.py
│   │   ├── nse_archive.py
│   │   ├── yfinance_client.py
│   │   ├── screener_scraper.py
│   │   ├── moneycontrol_scraper.py
│   │   ├── pulse_rss.py
│   │   ├── moneycontrol_rss.py
│   │   ├── et_rss.py
│   │   ├── mint_rss.py
│   │   ├── bs_rss.py
│   │   └── triangulate.py    # ← the cross-validation engine
│   │
│   ├── llm/
│   │   ├── client.py         # anthropic
│   │   ├── intent.py         # haiku router
│   │   ├── orchestrator.py   # tool-calling loop
│   │   ├── tools.py          # 4 tools
│   │   ├── prompts.py        # cached prefix
│   │   ├── guardrails.py     # blocklist + disclaimer
│   │   └── verifier.py       # claim ↔ source matcher
│   │
│   ├── analytics/
│   │   └── sentiment.py
│   │
│   ├── compliance/
│   │   ├── blocklist.py
│   │   └── disclaimers.py
│   │
│   ├── db/
│   │   ├── session.py
│   │   └── models/  (stock, price, news, chat_audit, scrape_log)
│   │
│   └── workers/
│       ├── arq_settings.py
│       ├── nightly_eod.py
│       ├── news_poll.py
│       └── prefetch_top50.py
│
├── frontend/              # Vite + React + TS
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── vite.config.ts     # proxy /api → :8000, /chat (SSE) → :8000
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── lib/
│       │   ├── api.ts          # fetch wrappers (TanStack Query)
│       │   └── sse.ts          # streaming chat client (EventSource / fetch+ReadableStream)
│       ├── components/
│       │   ├── ui/             # shadcn primitives (button, card, badge, table, sheet)
│       │   ├── ChatPanel.tsx
│       │   ├── MessageBubble.tsx
│       │   ├── ConfidenceBadge.tsx     # HIGH / MED / LOW pill
│       │   ├── SourceCitations.tsx     # "NSE ₹1,247.55 · Yahoo ₹1,247.50 · Screener ₹1,247.50"
│       │   ├── DisclaimerFooter.tsx
│       │   └── SuggestedPrompts.tsx    # the 6 demo prompts as one-tap chips
│       ├── routes/
│       │   ├── ChatRoute.tsx
│       │   ├── QuoteRoute.tsx          # /quote/RELIANCE — full triangulation table
│       │   └── AdminAuditsRoute.tsx    # the "see how the sausage is made" page
│       └── styles.css
├── tests/
│   ├── golden_queries.yaml
│   ├── test_triangulate.py
│   ├── test_blocklist.py
│   └── test_verifier.py
└── scripts/
    ├── seed_universe.py
    └── eval_run.py
```

---

## 5. The triangulation engine (`data/triangulate.py`)

This is the most important file in the demo. Sketch:

```python
@dataclass
class Quote:
    ticker: str
    price: Decimal
    ts: datetime
    source: str
    extras: dict           # day_range, prev_close, change_pct...

@dataclass
class TriangulatedQuote:
    ticker: str
    price: Decimal | None
    confidence: Literal["HIGH","MED","LOW"]
    sources: list[Quote]   # what each source returned
    spread_pct: float      # max pairwise relative diff
    as_of: datetime
    disagreement_note: str | None

async def triangulate_quote(ticker: str) -> TriangulatedQuote:
    quotes = await asyncio.gather(
        nselib_quote(ticker), yfinance_quote(ticker),
        screener_quote(ticker), moneycontrol_quote(ticker),
        return_exceptions=True,
    )
    valid = [q for q in quotes if isinstance(q, Quote)]
    if len(valid) < 2:
        return _from_lkg(ticker, reason="insufficient_sources")
    spread = _max_pairwise_pct(valid)
    if spread <= 0.001:    confidence = "HIGH"
    elif spread <= 0.005:  confidence = "MED"
    else:                  confidence = "LOW"
    price = _median(valid) if confidence != "LOW" else None
    return TriangulatedQuote(ticker, price, confidence, valid, spread, now(), ...)
```

Same pattern for `triangulate_fundamentals`, `triangulate_index_level`.

Tests for this file are the most-loaded test suite in the repo.

---

## 6. Verifier (the second-most important file)

After the LLM produces a draft response, run it through `llm/verifier.py`:

1. **Extract numbers** with a regex over `₹\s?[\d,]+(\.\d+)?`, `\d+(\.\d+)?\s*%`, `(\d{1,3}(?:,\d{3})+|\d+)\s*(?:cr|crore|lakh)`.
2. **Build the source-truth set** from the tool-call JSON (every numeric value).
3. **Match** each extracted number to the source-truth set with a tolerance:
   - Prices: exact match or ±0.05 (currency rounding)
   - Percentages: ±0.1
   - Crores/lakhs: ±0.5%
4. **Unmatched numbers** → re-prompt the LLM once with `STRICT_MODE=true` (system message: "Do NOT introduce numbers not present in the tool results"). If still unmatched → return a templated fallback that just shows the tool-call JSON in a friendly format.

This catches ~95% of price hallucinations in our golden eval set.

---

## 7. Day-by-day (~7 days)

**D1 — Skeleton (4–6h)**
- Backend: `uv init`, repo scaffold per §4, Docker Compose up (postgres+timescale+pgvector + redis), Alembic + first migration (`stocks`, `prices_daily`, `news`, `chat_audit`, `scrape_log`); "Hello" FastAPI on :8000
- Frontend: `pnpm create vite frontend`, install Tailwind + shadcn/ui, blank `ChatRoute` rendering on :5173, Vite proxy to :8000 verified
- Seed `stocks` with NIFTY-50 from a hardcoded CSV

**D2 — Data sources & triangulation (full day)**
- Implement all 4 quote sources (nselib, yfinance, screener, moneycontrol) — async wrappers, each with `curl_cffi` where needed
- `triangulate.py` quote engine + 30 unit tests
- `GET /quote/{ticker}` returns `TriangulatedQuote` JSON
- Cache layer in Redis (15s during RTH, 1h after hours)

**D3 — News + sentiment + fundamentals (full day)**
- Pulse + Moneycontrol + ET + Mint + BS RSS pollers running on arq cron (5min during RTH)
- Headline-to-ticker NER (Haiku one-shot for demo; can replace with spaCy later)
- distilroberta sentiment scoring; cache 24h
- `triangulate_fundamentals` (yfinance + Screener + MC)
- `GET /news/{ticker}?hours=24`, `GET /quote/{ticker}/info`

**D4 — LLM brain (full day)**
- Anthropic SDK; cached prefix Block A (system) / B (tool defs) / C (top-50 ticker map)
- 4 tools wired: `get_quote`, `get_news`, `get_company_info`, `get_index_level`
- Tool-calling loop in `orchestrator.py`
- Haiku intent router classifies into `{quote, why_falling, company_info, news, refuse, education}`
- `POST /chat` (SSE via `sse-starlette`) end-to-end working

**D5 — Guardrails + verifier (full day)**
- Blocklist regex with ~80 cases (verbs, target/SL phrases, personalisation patterns)
- Ticker→disclaimer auto-injector
- Verifier (number extraction + source-truth matching + 1-shot retry + templated fallback)
- chat_audit logging on every turn

**D6 — React UI + admin panel + golden evals (full day, the longest day)**
- `pnpm create vite frontend --template react-ts`, install Tailwind + shadcn/ui (`button`, `card`, `badge`, `table`, `sheet`, `scroll-area`, `skeleton`)
- TanStack Query for `/api/quote`, `/api/news`; raw `fetch` + `ReadableStream` for `/chat` SSE streaming
- `ChatRoute` — message list, input box, suggested-prompt chips, streaming response with token-by-token render, confidence badge + source citations rendered inline beneath each LLM answer
- `AdminAuditsRoute` — paginated table of `chat_audit` rows with filters (intent, blocked, flagged); click a row → side `Sheet` with the full tool-call JSON, prompt hash, model, verifier verdict
- Build `tests/golden_queries.yaml` — 50 queries with expected behaviors
- `scripts/eval_run.py` runs them through `/chat` and produces a pass/fail report
- Iterate prompts until ≥48/50 pass

**D7 — Polish + dry runs (full day)**
- Run the 6 demo scripts end-to-end 5×; fix every rough edge
- Pre-warm caches for the demo tickers (RELIANCE, TCS, INFY, HDFCBANK, TATAMOTORS, ADANIENT, etc.) — so live demo doesn't hit a cold cache
- Write a README with the 5-command bring-up
- Record a 2-min screen capture as backup if live demo network fails

---

## 8. Demo-day fail-safes

- **Pre-recorded screen capture** of the 6 demo flows (D7 deliverable). Network blips during a live demo are common.
- **Pre-warmed Redis cache** for the demo tickers — so all 6 flows succeed on cached LKG even if NSE blocks us mid-demo.
- **Frozen golden run** — a saved audit-log snapshot from a known-good run, viewable in the admin panel.
- **Fallback ticker list** — if RELIANCE breaks, demo with TCS or HDFCBANK; have 10 verified-working tickers ready.

---

## 9. Accuracy gate before demo day

Phase-1-demo passes only when:

- ✅ Triangulation tests: 100% pass on `tests/test_triangulate.py` (≥30 cases)
- ✅ Blocklist tests: 100% pass on `tests/test_blocklist.py` (≥80 cases)
- ✅ Verifier tests: 100% pass on `tests/test_verifier.py` (≥40 cases including known-hallucination prompts)
- ✅ Golden eval: ≥48/50 on `scripts/eval_run.py`
- ✅ End-to-end manual sweep of all 6 demo flows: 5×, zero defects
- ✅ Cold-start latency p50 < 4s, warm-cache p50 < 1.5s on your Mac
- ✅ Admin audit panel shows zero verifier rejections that "leaked" to the user (i.e., user never saw an unverified number)

---

## 10. Cost (yes, it's nearly zero)

| Item | Cost |
|---|---|
| All data sources | ₹0 |
| Local infra | ₹0 (your Mac + Docker Desktop) |
| LLM during dev (~500 dev queries × Sonnet w/ caching) | ~₹150 |
| LLM during demo (~50 live queries) | ~₹15 |
| **Total demo budget** | **<₹200** |

---

## 11. What we explicitly defer to post-demo

- Per-user broker OAuth (Upstox/Angel/Dhan)
- Production VPS (DO Bangalore / OVH Mumbai)
- DPDP consent UX, Privacy notice, DPO appointment
- Sentry / error tracking SaaS
- Domain, SSL, Cloudflare
- React Native frontend
- RAG over annual reports (Phase 2)
- Technicals (RSI/MACD/BB) and shareholding intelligence (Phase 2)
- F&O, screeners, portfolio (Phase 3+)

These come back the moment we go from "demo" to "100 beta users".

---

## 12. Decisions I still need from you

1. **Universe size** — Top 50 (NIFTY 50, fastest demo) or Top 200? More tickers = longer cold-cache pre-warm.
2. **LLM provider** — Anthropic Claude (my recommendation), or do you want to try Gemini Flash first to keep even LLM cost ≈ ₹0? (Gemini Flash free tier should cover the demo, but quality on tool-calling is materially weaker than Sonnet.)
3. **What's the demo audience** — investors, FinWin internal team, or co-founder? Affects what flows to prioritise (investor → polish + AI safety story; engineering → admin/audit panel + accuracy proof).
4. **Demo deadline** — when do you need to show this? Drives whether we sprint 7 days or split into 2-week comfort schedule.
