# Midas — Phase 1 Build Plan ("Informed Bot")

**Status:** Draft v1 · **Owner:** Abhishek · **Window:** Weeks 1–4 · **Date:** 2026-05-07

This document is the deeply-researched, opinionated build plan for Phase 1 of Midas. It is based on the original PDF + targeted research on (a) NSE/BSE scraping reality in 2026, (b) the LLM/AI landscape in 2026, (c) SEBI compliance, and (d) infra-stack picks. **Where I deviate from the PDF I call it out explicitly** so you can push back.

---

## 0. TL;DR — What changes vs. the original PDF

| Area | Original PDF | Plan v1 (this doc) | Why |
|---|---|---|---|
| **LLM** | "GPT-5.5 / Gemini 3 Pro" | **Claude Sonnet 4.5+** as workhorse, **Haiku 4.5** as router, **Gemini 2.5 Flash / Groq** as free-tier overflow. Pin exact model IDs. | "GPT-5.5" doesn't exist (verified by training cutoff). Claude Sonnet has the strongest tool-use + 1h prompt caching for our RAG-heavy workload. |
| **Vector DB** | Qdrant (separate daemon) | **pgvector inside Postgres** | At 5M chunks max, pgvector + HNSW is enough. One less daemon, one less backup target. Qdrant is a Phase-3 upgrade. |
| **Job queue** | Celery | **arq** (async, Redis-only, by Pydantic team) | Celery is sync-first and heavyweight. arq fits FastAPI's async stack and we only run ~100 jobs/night. |
| **Indicators lib** | `pandas-ta` | **pin `pandas-ta` 0.3.14b OR `pandas-ta-classic` fork** + **TA-Lib for hot indicators** | Original `pandas-ta` is unmaintained since 2023; community forked it. |
| **Historical data** | `jugaad-data` | **Direct HTTP to `nsearchives.nseindia.com`** | `jugaad-data` is dead (no meaningful commits since 2023). NSE moved bhavcopy to `nsearchives.*` with new format in mid-2024. |
| **HTTP client** | `requests` + BS4 | **`httpx`** for clean APIs + **`curl_cffi`** (TLS-fingerprint impersonation) for any host behind Cloudflare/Akamai (NSE, Screener) | NSE/BSE check JA3 fingerprints. Plain `requests` from a cloud IP gets challenged. `curl_cffi` mimics Chrome TLS. |
| **Sentiment model** | FinBERT | **`mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis`** (CPU-cheap) baseline; FinGPT-Forecaster as Phase 2 upgrade | FinBERT is from 2019; better/faster open models exist. |
| **VPS** | Hetzner | **DigitalOcean Bangalore or OVH Mumbai** (5–20ms latency to India) instead of Hetzner EU (~150ms) | Latency to Indian users matters for an interactive chat. |
| **Streaming** | "SSE behind Cloudflare" | **SSE on a non-CF subdomain** (`stream.mrmarket.app` set to "DNS only") | CF free/pro buffers responses. Streaming feels broken otherwise. |
| **🚨 Data-fanout legality** | Implicit "scrape NSE → serve all users" | **Per-user broker OAuth (Upstox/Angel/Dhan/Fyers) for live quotes; cached EOD bhavcopy + Pulse RSS + GDELT for everything else** | Re-distributing one broker token's data to 50k users violates every Indian broker's ToS and possibly NSE data licensing. We must architect for per-user OAuth from day 1, even at 100 users. **This is the single biggest correction to the original PDF.** |
| **🚨 SEBI safe-harbor** | "Disclaimer + frame as technical observation" | **Hard-blocklist of recommendation verbs + factual-only output for Phase 1 + audit log of every prompt/response** | Phase 1 stays in factual/news territory (no buy/sell/hold/target language) → no IA/RA registration needed. The moment we say "buy" or "target ₹X" we cross into RA territory. |

---

## 1. Phase 1 Charter

**What "Phase 1" delivers (per PDF):**
1. Live price queries ("What is the price of Reliance?")
2. Why-is-X-falling explanations (price + cited news + sentiment)
3. Basic company info (sector, market cap, key ratios — read-only summary)
4. News fetching + sentiment scoring per ticker

**Goals:** 100 beta users · ≥95% factual accuracy · <3s end-to-end p95 latency · zero SEBI compliance incidents.

**Explicitly NOT in Phase 1** (deferred to Phase 2+):
- Stock recommendations, targets, stop-losses (RA-territory)
- Portfolio analysis (needs Demat OAuth + UX)
- F&O / derivatives queries (regulatory surface)
- RAG over annual-report PDFs (Phase 2 — needs Qdrant or pgvector tuning)
- Custom screeners (Phase 3)

**Acceptance gate to call Phase 1 "done":**
- 50-query golden-set eval suite passes ≥48/50 with no false numbers
- All scraper sources have a fallback chain that survives one source going dark
- Every LLM response carries the master + inline disclaimer
- Hard-blocklist regex blocks all recommendation verbs in 100% of test cases
- Audit log captures (prompt, retrieved context, output, user_id, ts) for every chat
- Sentry shows zero unhandled exceptions on the last 24h of test traffic

---

## 2. The Big Risks (Read This First)

### 2.1 The data-redistribution legal trap (most important)
- **NSE/BSE scraping is technically fragile and legally grey** — both exchanges use Akamai bot management (cookie + JA3 + rate limits), and there is no public free API.
- **Broker APIs (Upstox, Angel One, Dhan, Fyers) are licensed for the authenticated user's own consumption.** One broker token cannot legally fan out market data to 50,000 of *your* users. Smallcase, Sensibull, Tickertape all work this way: each user OAuths their own broker.
- **Implication for Phase 1:** Even at 100 beta users, design for per-user broker OAuth as the source for live/intraday data. For pre-login pages and aggregate market views, use Yahoo Finance (delayed, disclaimed) and our own EOD bhavcopy from `nsearchives.nseindia.com`.
- **Phase-1 user model:** Beta users link a broker (Upstox is easiest — free, permissive scope, good DX). If they don't link, they get EOD-delayed data with a disclaimer.

### 2.2 The SEBI line we will not cross
The bot must never:
- Use imperative recommendation verbs: *buy, sell, exit, accumulate, book profit, trim, load up, SIP this, target, stop-loss at*
- Combine user portfolio data + a security-specific recommendation in the same output
- Set price targets or "fair values"
- Recommend F&O strategies or intraday entries
- Personalize a recommendation from risk profile

The bot **may** (Phase-1 sweet spot):
- Quote current/EOD prices with timestamp + source
- Summarize news headlines with citations
- Explain what an event/term means (educational)
- Report consensus analyst ratings *as a fact about what others said*, with source

### 2.3 Scraper bus-factor
`nselib`, `nsepython`, `bseindiaapi`, `bsedata` are all single-maintainer projects. They break ~weekly when NSE rotates Akamai cookies, with 1–7 day fix lag. **We must implement a fallback chain** (primary → secondary → cached last-known-good) and never have a single source on the critical path.

### 2.4 Prompt caching is a survival-grade cost lever
At ~1k queries/day with ~10K-token system+context prefix, uncached input cost dominates. Anthropic's 1-hour prompt cache (~90% read discount) cuts our LLM bill by ~70%. **Design every LLM call from day 1 to put stable prefixes in the cached block.**

---

## 3. Final Tech Stack (Phase 1)

```
┌──────────────────────────── INFRA ────────────────────────────┐
│ VPS:        DigitalOcean Bangalore Premium AMD 4vCPU/8GB     │
│             (~$48/mo ≈ ₹4,000), or OVH VPS Comfort Mumbai    │
│ Container:  Docker Compose (single host) + Caddy (auto-TLS)  │
│ DB:         Postgres 16 + TimescaleDB Community + pgvector   │
│ Cache:      Redis 7                                          │
│ Job queue:  arq (Redis-backed, async)                        │
│ Storage:    VPS disk + nightly rsync to Hetzner Storage Box  │
│ Backup:     pg_dump nightly → S3-compatible (Backblaze B2)  │
└───────────────────────────────────────────────────────────────┘

┌─────────────────────────── BACKEND ───────────────────────────┐
│ Lang:       Python 3.12                                      │
│ Deps:       uv + pyproject.toml + uv.lock                    │
│ Web:        FastAPI 0.115+ + uvicorn (4 workers) + granian?  │
│ Streaming:  sse-starlette on stream.mrmarket.app (no CF)     │
│ HTTP:       httpx (async) + curl_cffi (TLS-impersonate)      │
│ Browser:    Playwright async (only when JS required)         │
│ Schemas:    Pydantic v2 everywhere                           │
│ Migrations: Alembic                                          │
│ Logs/Trace: Pydantic Logfire (free tier) + Sentry SDK        │
└───────────────────────────────────────────────────────────────┘

┌────────────────────────── DATA LAYER ─────────────────────────┐
│ Live quotes:   Per-user broker OAuth (Upstox v2 first)       │
│ EOD bars:      Direct HTTP → nsearchives.nseindia.com        │
│ Fundamentals:  yfinance (.NS/.BO) cached, link-out to        │
│                Screener for deep dives (no scraping at scale) │
│ News:          Pulse RSS (Zerodha) + Moneycontrol RSS +      │
│                ET Markets RSS + GDELT 2.0 BigQuery (15-min)  │
│ Corporate acts: nselib (primary) + bseindiaapi (BSE-only)    │
│ Cross-validate: yfinance secondary → confidence score        │
└───────────────────────────────────────────────────────────────┘

┌────────────────────────── INTELLIGENCE ───────────────────────┐
│ LLM (work):    Claude Sonnet 4.5+ (anthropic SDK, prompt     │
│                cache 1h TTL, tool use)                        │
│ LLM (route):   Claude Haiku 4.5 (intent classifier, ticker   │
│                NER, refusal classifier)                       │
│ LLM (free):    Gemini 2.5 Flash + Groq Llama-3.3-70B fallback │
│ Sentiment:     mrm8488/distilroberta-financial-news (CPU)    │
│ Indicators:    pandas-ta-classic (Phase-1 read only — Phase 2)│
│ Embeddings:    text-embedding-3-small (Phase 2 / RAG)         │
│ Vector store:  pgvector + HNSW (Phase 2)                      │
└───────────────────────────────────────────────────────────────┘
```

**Pin every model ID and dep version.** No `latest` aliases.

---

## 4. Architecture (Phase 1)

```
                       ┌──────────────────────┐
                       │   FinWin App / Web   │  ← React Native + web fallback
                       │   /chat UI           │
                       └──────────┬───────────┘
                                  │ HTTPS, JWT
                                  ▼
                  ┌──────────────────────────────┐
                  │  api.mrmarket.app (Caddy)    │ ← Cloudflare proxy OK
                  └──────────┬───────────────────┘
                             ▼
               ┌──────────────────────────────────┐
               │   FastAPI app (uvicorn workers)  │
               │                                  │
               │   ┌──────────────────────────┐   │
               │   │  /chat   /quote/{ticker} │   │
               │   │  /news/{ticker}          │   │
               │   │  /healthz                │   │
               │   └─────────────┬────────────┘   │
               │                 ▼                │
               │   ┌──────────────────────────┐   │
               │   │  IntentRouter (Haiku)    │   │
               │   │  → {quote, why_falling,  │   │
               │   │     company_info, news,  │   │
               │   │     refuse, education}   │   │
               │   └─────────────┬────────────┘   │
               │                 ▼                │
               │   ┌──────────────────────────┐   │
               │   │  Tool Orchestrator       │   │
               │   │  • get_quote(ticker)     │   │
               │   │  • get_news(ticker, n)   │   │
               │   │  • get_company_info(t)   │   │
               │   │  • get_index_level(idx)  │   │
               │   └─────────────┬────────────┘   │
               │                 ▼                │
               │   ┌──────────────────────────┐   │
               │   │  Sonnet 4.5 (cached      │   │
               │   │  system+tool prefix)     │   │
               │   │  + tool calling loop     │   │
               │   └─────────────┬────────────┘   │
               │                 ▼                │
               │   ┌──────────────────────────┐   │
               │   │  Output Guardrail        │   │
               │   │  - regex blocklist       │   │
               │   │  - ticker→disclaimer     │   │
               │   │  - claim verifier        │   │
               │   └─────────────┬────────────┘   │
               │                 ▼                │
               │   ┌──────────────────────────┐   │
               │   │  SSE stream (non-CF sub) │   │
               │   └──────────────────────────┘   │
               └────┬─────────────────┬───────────┘
                    │                 │
       ┌────────────┘                 └────────────┐
       ▼                                           ▼
┌─────────────┐                          ┌──────────────────┐
│ Postgres 16 │                          │     Redis 7      │
│ +Timescale  │                          │ price:{ticker}5s │
│ +pgvector   │                          │ news:{ticker}5m  │
│             │                          │ llm:{hash}1h     │
│ stocks      │                          └──────────────────┘
│ prices      │                                  ▲
│ news        │                                  │
│ scrape_log  │                                  │
│ chat_audit  │                                  │
└──────┬──────┘                                  │
       │                                         │
       ▼                                         │
┌─────────────────────────────────────────────────────────────┐
│   arq worker (cron jobs)                                    │
│   - 03:30 IST: download nsearchives bhavcopy                │
│   - 04:00 IST: yfinance fundamentals refresh (top-200)      │
│   - every 5min RTH: Pulse RSS + Moneycontrol RSS poll       │
│   - every 15min: GDELT news ingest + sentiment              │
│   - hourly: scraper-health smoke tests                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Repo Layout

Smaller than the PDF's layout, because Phase 1 doesn't need analytics/RAG modules yet.

```
midas/
├── README.md
├── pyproject.toml          # uv-managed
├── uv.lock
├── docker-compose.yml      # api, worker, postgres, redis, caddy
├── docker-compose.prod.yml # overrides for prod
├── Dockerfile              # multi-stage: ta-lib build + slim runtime
├── Caddyfile
├── alembic.ini
├── .env.example
│
├── app/
│   ├── main.py             # FastAPI app factory
│   ├── config.py           # pydantic-settings
│   ├── deps.py             # FastAPI Depends() helpers
│   │
│   ├── api/
│   │   ├── chat.py         # /chat (SSE)
│   │   ├── quote.py        # /quote/{ticker}
│   │   ├── news.py         # /news/{ticker}
│   │   ├── health.py       # /healthz
│   │   └── auth.py         # broker OAuth callback (Upstox)
│   │
│   ├── llm/
│   │   ├── client.py       # Anthropic + Gemini + Groq adapters
│   │   ├── intent.py       # Haiku-based router
│   │   ├── orchestrator.py # tool-calling loop
│   │   ├── tools.py        # tool schemas + dispatch
│   │   ├── prompts.py      # cached system prefix
│   │   ├── guardrails.py   # output blocklist + disclaimer
│   │   └── verifier.py     # claim ↔ source matching
│   │
│   ├── data/
│   │   ├── nse_archive.py  # nsearchives bhavcopy fetch
│   │   ├── nselib_client.py
│   │   ├── bse_client.py
│   │   ├── yfinance_client.py
│   │   ├── upstox_oauth.py # per-user broker auth
│   │   ├── upstox_quote.py
│   │   ├── pulse_rss.py
│   │   ├── moneycontrol_rss.py
│   │   ├── gdelt.py
│   │   └── cross_validate.py
│   │
│   ├── analytics/
│   │   └── sentiment.py    # distilroberta CPU inference
│   │
│   ├── db/
│   │   ├── base.py         # SQLAlchemy 2.0 async
│   │   ├── session.py
│   │   └── models/
│   │       ├── stock.py
│   │       ├── price.py
│   │       ├── news.py
│   │       ├── chat_audit.py
│   │       ├── scrape_log.py
│   │       └── user.py
│   │
│   ├── workers/
│   │   ├── arq_settings.py
│   │   ├── nightly_eod.py
│   │   ├── news_poll.py
│   │   └── health_smoke.py
│   │
│   └── compliance/
│       ├── blocklist.py    # regex/phrase list
│       ├── disclaimers.py  # all canonical disclaimer strings
│       └── audit.py        # write to chat_audit table
│
├── migrations/             # alembic
├── tests/
│   ├── golden_queries.yaml # 50-query eval set
│   ├── test_blocklist.py
│   ├── test_scrapers.py
│   └── ...
└── scripts/
    ├── seed_universe.py    # load top-500 tickers
    └── eval_run.py         # run golden set against staging
```

---

## 6. Database Schema (Phase 1 only)

```sql
-- Universe of tickers we cover
CREATE TABLE stocks (
  ticker         TEXT PRIMARY KEY,        -- e.g. RELIANCE
  exchange       TEXT NOT NULL,           -- NSE | BSE
  yahoo_symbol   TEXT,                    -- RELIANCE.NS
  isin           TEXT UNIQUE,
  name           TEXT NOT NULL,
  sector         TEXT,
  industry       TEXT,
  market_cap_inr BIGINT,
  active         BOOLEAN DEFAULT TRUE,
  meta           JSONB,
  updated_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ix_stocks_active ON stocks(active);

-- EOD bars (Timescale hypertable)
CREATE TABLE prices_daily (
  ticker       TEXT NOT NULL REFERENCES stocks(ticker),
  ts           TIMESTAMPTZ NOT NULL,        -- close-of-day ts in IST
  open         NUMERIC(12,4),
  high         NUMERIC(12,4),
  low          NUMERIC(12,4),
  close        NUMERIC(12,4) NOT NULL,
  prev_close   NUMERIC(12,4),
  volume       BIGINT,
  delivery_qty BIGINT,
  source       TEXT NOT NULL,               -- 'nsearchives' | 'yfinance'
  PRIMARY KEY (ticker, ts, source)
);
SELECT create_hypertable('prices_daily','ts', chunk_time_interval => INTERVAL '30 days');

-- Cross-validation outcomes
CREATE TABLE price_check (
  ticker       TEXT NOT NULL,
  ts           TIMESTAMPTZ NOT NULL,
  primary_src  TEXT,
  primary_val  NUMERIC(12,4),
  secondary    JSONB,                       -- {yfinance: 1247.55, nse: 1247.50}
  confidence   TEXT,                        -- HIGH | MEDIUM | LOW
  delta_bps    INT,                         -- |a-b|/a in basis points
  PRIMARY KEY (ticker, ts)
);

-- News
CREATE TABLE news (
  id           BIGSERIAL PRIMARY KEY,
  source       TEXT NOT NULL,               -- pulse | moneycontrol | et | gdelt
  url          TEXT UNIQUE,
  title        TEXT NOT NULL,
  body         TEXT,
  published_at TIMESTAMPTZ NOT NULL,
  fetched_at   TIMESTAMPTZ DEFAULT NOW(),
  tickers      TEXT[],                      -- ['RELIANCE','TCS']
  sentiment    NUMERIC(4,3),                -- -1..+1
  sentiment_label TEXT,                     -- positive|negative|neutral
  meta         JSONB
);
CREATE INDEX ix_news_published ON news(published_at DESC);
CREATE INDEX ix_news_tickers ON news USING GIN (tickers);

-- Scraper health
CREATE TABLE scrape_log (
  id          BIGSERIAL PRIMARY KEY,
  source      TEXT NOT NULL,
  ts          TIMESTAMPTZ DEFAULT NOW(),
  ok          BOOLEAN NOT NULL,
  status_code INT,
  duration_ms INT,
  error       TEXT,
  meta        JSONB
);
CREATE INDEX ix_scrape_log_recent ON scrape_log(source, ts DESC);

-- Users (Phase-1: minimal, broker linking optional)
CREATE TABLE users (
  id              BIGSERIAL PRIMARY KEY,
  finwin_user_id  TEXT UNIQUE NOT NULL,
  email           TEXT,
  broker          TEXT,                     -- upstox | angel | dhan | null
  broker_token    TEXT,                     -- encrypted at rest (KMS / pgcrypto)
  broker_expiry   TIMESTAMPTZ,
  consents        JSONB NOT NULL DEFAULT '{}',
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Audit trail (regulatory & evals)
CREATE TABLE chat_audit (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT REFERENCES users(id),
  ts          TIMESTAMPTZ DEFAULT NOW(),
  query       TEXT NOT NULL,
  intent      TEXT,
  retrieved   JSONB,                        -- {tools_called, results}
  prompt_hash TEXT,                          -- hash of cached prefix used
  model       TEXT,
  output      TEXT,
  blocked     BOOLEAN DEFAULT FALSE,         -- guardrail rejected
  flagged     JSONB,                         -- {verbs_hit:[...]}
  latency_ms  INT,
  cost_inr    NUMERIC(8,4)
);
CREATE INDEX ix_chat_audit_user_ts ON chat_audit(user_id, ts DESC);
```

---

## 7. The LLM/Agent Design

### 7.1 Cached system prefix (Anthropic prompt cache, 1h TTL)
- **Block A — System prompt** (~2K tokens): Midas personality, scope, refusal patterns, blocklist rules, disclaimer rules. Frozen at deploy time.
- **Block B — Tool definitions** (~2K tokens): JSON schemas for `get_quote`, `get_news`, `get_company_info`, `get_index_level`.
- **Block C — Static market context** (~3K tokens): list of top-500 ticker→name→sector mapping, holiday calendar, market hours.
- **Suffix (uncached)**: user query + tool results.

This prefix is identical across all users and refreshes every hour. Read cost ≈ 10% of normal input tokens. With ~7K cached tokens × 1k queries/day, savings ≈ ₹X/day vs uncached (model-dependent).

### 7.2 Tool catalog (Phase 1)
| Tool | Inputs | Returns |
|---|---|---|
| `get_quote(ticker)` | ticker, prefer_realtime?: bool | `{price, ts, source, change_pct, day_range, prev_close, confidence}` |
| `get_company_info(ticker)` | ticker | `{name, sector, industry, market_cap, key_ratios, source, as_of}` |
| `get_news(ticker, lookback_hours)` | ticker, hours (default 24) | `[{title, url, source, published_at, sentiment, sentiment_label}]` |
| `get_index_level(symbol)` | NIFTY50 / SENSEX / BANKNIFTY | `{level, change_pct, ts, source}` |

All tools return **structured JSON with explicit timestamps and source**, never prose. The LLM is instructed to weave timestamps into its narrative ("as of 14:32 IST").

### 7.3 Output guardrails (the SEBI moat)
1. **Hard regex blocklist** — reject (or rewrite to refusal) any output matching:
   - Verbs: `\b(buy|sell|exit|short|accumulate|book\s+profit|trim|load\s+up|SIP\s+this)\b` (case-insensitive)
   - Targets: `target\s+(?:price\s+)?(?:of\s+)?₹?\s*\d`, `stop[- ]?loss\s+(at|of)`, `entry\s+(at|near|around)`
   - Personalisation: `(should|must)\s+you\s+(buy|invest|exit)`, `for\s+your\s+portfolio`
2. **Ticker→disclaimer injector** — if any ISIN/ticker token appears in output, auto-append the inline disclaimer.
3. **Claim verifier** — extract numeric claims (price, %, ₹) and verify each appears in the tool-result JSON. If not, re-prompt once with `STRICT_MODE=true`. Twice = surface a "couldn't verify" message.
4. **Audit log** — write `chat_audit` row before sending to user. If blocked, store the rejected output too for later review.

### 7.4 Refusal templates (canonical — used verbatim)
- "I can't recommend buying or selling specific securities. I can share factual information about [X] — would you like the latest results summary, business segments, or recent price action?"
- "I can't set price targets. I can share recent broker consensus targets reported in the news, with sources, if you want."
- "Derivatives carry significant risk. As per SEBI's 2024 study, ~9 in 10 retail F&O traders incurred net losses. I can explain how options work in general, but I can't suggest a specific trade."

### 7.5 Master + inline disclaimers (always-on)
**Master (every screen, fixed footer):**
> The information provided by Midas is for general informational and educational purposes only and does not constitute investment advice, a recommendation to buy or sell any security, or a solicitation. Midas is not a SEBI-registered Investment Adviser or Research Analyst. Investments in securities are subject to market risks. Past performance is not indicative of future results. Please consult a SEBI-registered Investment Adviser before making any investment decision.

**Inline (auto-appended whenever a ticker is named):**
> This is factual market information, not a recommendation.

---

## 8. Data Pipelines (Phase 1)

### 8.1 Live quotes
- **Logged-in user with linked Upstox:** call Upstox v2 `/market-quote/quotes` with their token. ~150ms.
- **Logged-in user without broker, or pre-login:** Yahoo `.NS` last-close, **labelled "Delayed (EOD)"**. Cached 5m.
- **Never** scrape NSE for real-time and serve to multiple users.

### 8.2 EOD bars (nightly, 03:30 IST)
1. arq worker fetches `https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip` with `httpx` + UA header. Parse new column format.
2. Same for BSE (`bseindia.com/download/BhavCopy/...`).
3. Upsert into `prices_daily` with `source='nsearchives'`.
4. Cross-validate with yfinance for top-200 tickers; record `delta_bps` in `price_check`.
5. Alert if `delta_bps > 50` (>0.5% mismatch) for any of NIFTY-50.

### 8.3 News ingest (every 5–15 min during RTH, hourly off-hours)
- **Pulse RSS** (`pulse.zerodha.com/feed.php`) — primary breadth feed. Cache last-seen-id to avoid dupes.
- **Moneycontrol RSS** + **ET Markets RSS** + **Mint RSS** + **BS RSS** as redundancy.
- **GDELT 2.0 GKG** via BigQuery — pull every 15 min for `India + finance` topics. Free with small BQ scan cost.
- For each headline: NER-extract tickers (Haiku one-shot or a small spaCy model with custom NER); compute sentiment with the distilroberta model; insert into `news`.

### 8.4 Fundamentals (nightly, top-200)
- yfinance `Ticker(t).info` → store last refresh in `stocks.meta`. Phase 1 only uses these for "company info" responses.
- Phase 2: license a fundamentals vendor (Tickertape/Trendlyne/EOD-HD).

### 8.5 Scraper resilience
Every scraper inherits `BaseScraper`:
- 3 retry attempts with exponential backoff via `tenacity`
- timeouts (connect 5s, read 15s)
- one fallback chain wired in (`primary → secondary → cached_lkg`)
- writes to `scrape_log` on every call
- `health_smoke.py` runs hourly: hit each source with one canary call, alert via Sentry if 3 consecutive fails

---

## 9. Week-by-Week Implementation (28 days)

This is the actual day-by-day schedule for Phase 1. It folds the PDF's Days 1–7 (Foundation) + Days 8–14 (Intelligence) into Weeks 1–2, then adds Weeks 3–4 for hardening and beta launch.

### Week 1 — Skeleton & data ingestion
- **D1 (Mon)**: `uv` project init, repo scaffold (Section 5), Docker Compose up (Postgres+Timescale+pgvector, Redis), Caddy fronting "hello" FastAPI, Sentry+Logfire wired, GitHub repo + Actions CI (lint, mypy, test).
- **D2**: SQLAlchemy 2.0 async + Alembic; create all tables from Section 6; seed `stocks` with NIFTY-500 from a CSV.
- **D3**: NSE archive bhavcopy fetcher (`data/nse_archive.py`); arq worker boots; nightly job downloads + parses bhavcopy into `prices_daily`. Run for last 30 days as a backfill.
- **D4**: yfinance client + cross-validation logic → `price_check`. Alert wired.
- **D5**: BSE bhavcopy ingest + nselib client for live quotes (logged-in fallback when no Upstox).
- **D6**: Pulse RSS + Moneycontrol RSS poller. Insert into `news`. Dedupe by URL.
- **D7**: distilroberta sentiment model (HuggingFace transformers, CPU inference). Score every news row. Verify positive/negative labels look sane on 50 hand-checked items.

**Exit Week 1:** `prices_daily` has last 30 days for top-500. `news` has last 24h with sentiment. All scrapers write to `scrape_log`. Health smoke job green.

### Week 2 — LLM brain & guardrails
- **D8**: Anthropic SDK setup, prompt-cache structure (Block A/B/C). System prompt v1 written. Tool schemas defined as Pydantic models.
- **D9**: Tool dispatch (`llm/tools.py`) wired to data layer. Unit tests for each tool.
- **D10**: Tool-calling loop (`llm/orchestrator.py`) — Sonnet 4.5 with cached prefix. SSE streaming via `sse-starlette` on `stream.mrmarket.app` (DNS-only subdomain). End-to-end "What is the price of Reliance?" works.
- **D11**: IntentRouter (Haiku) — classify into `{quote, why_falling, company_info, news, refuse, education, other}`. Add to FastAPI middleware.
- **D12**: Output guardrails — regex blocklist, ticker→disclaimer injector, claim verifier. Re-prompt-once flow for unverified claims.
- **D13**: chat_audit logging on every turn. Build a tiny `/admin/audits` read-only endpoint (basic-auth) for review.
- **D14**: Streamlit (or simple HTML/htmx) chat UI for internal testing. Deploy preview to staging VPS.

**Exit Week 2:** Internal team can chat with Midas. The 4 tools work. Disclaimers + blocklist tested.

### Week 3 — Hardening, evals, broker OAuth
- **D15**: Build the **golden eval set** — 50 hand-crafted queries with expected behavior labels (`{should_quote, should_refuse, should_explain, should_link_news}`). Add `scripts/eval_run.py`.
- **D16**: Run evals → fix prompt + tool issues. Iterate until ≥48/50 pass on a single run.
- **D17**: Upstox v2 OAuth flow — `/auth/upstox/start` → `/auth/upstox/callback` → store encrypted token in `users.broker_token`. Use pgcrypto for encryption.
- **D18**: Live-quote path: when user has `users.broker_token`, route through Upstox. Disclaimer changes to "live" instead of "delayed".
- **D19**: Rate limits + retry/backoff on every external call (`tenacity`). LLM 429 → fallback chain (Sonnet → Gemini Flash → Haiku → static "I'm temporarily down" message).
- **D20**: DPDP compliance pass — consent screen, privacy notice, data-export endpoint, delete-my-data endpoint. Data Protection Officer contact in footer.
- **D21**: Load test (locust) — simulate 50 concurrent users for 1 hour. Tune uvicorn workers and Postgres pool. Publish capacity numbers.

**Exit Week 3:** ≥48/50 evals pass, Upstox OAuth round-trip works, DPDP basics in place, load-tested for 50 concurrent users.

### Week 4 — Beta launch
- **D22**: Production VPS provision (DO Bangalore Premium 4vCPU/8GB). Docker Compose prod overrides. Caddy SSL. Backups configured (`pg_dump → B2`).
- **D23**: Deploy to prod. Run golden evals against prod. Sentry+Logfire dashboards verified.
- **D24**: Internal alpha — invite team (~10 people) to use it for a half-day. Triage issues.
- **D25**: Fix top 10 issues from alpha. Tighten disclaimers based on actual outputs seen.
- **D26**: Beta invite cohort 1 (25 users). Gate by signup form + manual approval. Logfire dashboard tracks queries/user, refusal rate, blocklist-trigger rate.
- **D27**: Beta cohort 2 (75 more, total 100). Daily standup on metrics.
- **D28**: Phase-1 retro. Compile metrics dashboard (KPI table from §10). Decide go/no-go for Phase 2.

**Exit Phase 1:** 100 active beta users, ≥95% factual accuracy on golden + spot-checks, zero compliance incidents, p95 < 3s.

---

## 10. Phase 1 Success Metrics

| Category | KPI | Target |
|---|---|---|
| **Reliability** | Scraper uptime (any one source up per category) | >99% |
| | Cross-val mismatch rate | <0.5% |
| | LLM API uptime (with fallback) | >99.9% |
| | Sentry unhandled errors / 1k queries | <2 |
| **Accuracy** | Golden-set pass | ≥48/50 |
| | Verifier rejection rate | <2% |
| | User-reported wrong facts | <1 / 100 users / week |
| **Compliance** | Blocklist hit on output | 0 leaks / 1k queries |
| | Disclaimer present on every chat | 100% |
| | Audit trail completeness | 100% |
| **Performance** | Time-to-first-token (p50) | <1s |
| | Full response latency (p95) | <3s |
| **Cost** | Cost per query (LLM only) | <₹0.50 (target: ₹0.20 with cache) |
| **Engagement (informational)** | Queries/user/day | track only |
| | D7 retention | track only |

---

## 11. Cost Projection (Phase 1, 100 users)

| Line item | INR/month |
|---|---|
| DigitalOcean Bangalore Premium 4vCPU/8GB | ~4,000 |
| Domain + SSL (Caddy = free) | ~100 |
| Sentry free tier | 0 |
| Logfire free tier | 0 |
| Backblaze B2 backups | ~100 |
| Anthropic Sonnet 4.5 (1k queries/day, ~7k cached + 2k uncached + 600 out) — **with 1h cache** | ~3,000–6,000 |
| Anthropic Haiku 4.5 (intent + NER) | ~500 |
| Gemini Flash overflow / dev | 0 (free tier) |
| GDELT BigQuery scans | <500 |
| **Total Phase 1 / month** | **₹8,000–12,000** |

(Original PDF said ~₹600/month for MVP relying on free LLM tier — that's only realistic if you accept Gemini Flash quality and free-tier rate limits, which I don't recommend for an "accuracy ≥95%" goal.)

---

## 12. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| NSE rotates Akamai cookies → all bhavcopy fetches 403 | Medium | High | `nsearchives.*` is friendlier than `www.*`; if even that breaks, fall back to yfinance EOD. Have the fix be a UA/header tweak, not a library bump. |
| `nselib`/`nsepython` upstream broken for >24h | Medium | Med | We don't depend on them on the user critical path — only nightly jobs. Wait it out or hit endpoints directly. |
| Yahoo Finance throttles | Low–Med | Med | Cache aggressively, batch tickers per request, keep a `delta_bps` widget visible so we notice quality degradation. |
| Anthropic outage | Low | High | Fallback chain → Gemini Flash → Haiku → graceful degraded message. Pre-test that path on D19. |
| LLM hallucination slips past verifier | Med | High | Verifier checks every numeric claim; audit log lets us catch and tune. Phase-1 surface area is narrow (4 tools), so hallucination space is small. |
| SEBI complaint about an output | Low | Catastrophic | Audit log + blocklist + factual-only framing. Have a securities-law firm review the system prompt + 100 sampled outputs before public beta. |
| DPDP non-compliance | Low | High | D20 sprint covers it. DPO contact published. |
| Scraping legality challenge | Low | Med | Phase 1 only scrapes EOD (public bhavcopy) and RSS. No real-time fanout. |
| Cost spike from prompt-cache miss | Med | Low | Logfire alerts on cache-hit-rate <70%. Investigate prefix drift. |

---

## 13. What I Recommend We Do Differently from the PDF (consolidated)

1. **Replace "GPT-5.5 / Gemini 3 Pro"** with **Claude Sonnet 4.5+ as workhorse, Haiku 4.5 as router, Gemini Flash + Groq as free overflow.** Pin model IDs.
2. **Drop Qdrant from Phase 1.** Use pgvector when RAG arrives in Phase 2.
3. **Drop Celery, use arq.** Saves a daemon and matches our async stack.
4. **Drop `jugaad-data`.** Use direct HTTP to `nsearchives.nseindia.com`.
5. **Add `curl_cffi`** for TLS fingerprint impersonation — without it we *will* get blocked.
6. **Architect for per-user broker OAuth** (Upstox first) from day 1, even at 100 users — this is a legal/redistribution requirement, not a scaling concern.
7. **Move VPS from Hetzner EU to DO Bangalore or OVH Mumbai** — latency to Indian users matters.
8. **Put SSE on a non-CF subdomain** — Cloudflare buffers responses on free/pro tiers.
9. **Replace FinBERT with `distilroberta-financial-news-sentiment`** — same job, smaller and newer.
10. **Add a hard regex blocklist + ticker→disclaimer injector** as compliance scaffolding, not just a "frame as technical observation" rule.
11. **Add a 50-query golden eval set + audit log** as Phase-1 exit gates — this catches regressions before users do.
12. **Get a SEBI-securities-law sign-off** on the system prompt + 100 sample outputs before public beta. Khaitan / Cyril / Nishith Desai / Trilegal all have practices for this.

---

## 14. Open Questions for You

Before I start cutting code, I need decisions on:

1. **Broker partner** — is FinWin already a Trading Member, or do we need to integrate with external brokers? (Affects whether we go Upstox/Angel/Dhan or directly use FinWin's own brokerage backend.)
2. **Hosting** — DO Bangalore (~₹4k/mo, ~5ms latency) vs Hetzner EU (~₹1.4k/mo, ~150ms)? Latency matters for chat feel.
3. **Brand legal entity** — what entity name carries the disclaimer? Same as FinWin, or a separate sub-brand? Affects who gets the SEBI letter if one comes.
4. **LLM budget** — comfortable with ₹8–12k/mo for 100-user Phase 1? Or do we cap at free tier and accept lower quality?
5. **Model lock-in** — do you want a hard pin to Claude Sonnet 4.5, or an abstraction (LiteLLM-like) to swap providers? I'd argue: pin for Phase 1, abstract in Phase 2.
6. **Beta-user gating** — invite-only with manual approval, or open to anyone with a FinWin account? Compliance argues for invite-only initially.
7. **Frontend target** — React Native first, or web first (faster to iterate)? PDF says React Native; web is faster to ship for a 100-user beta.

---

## 15. References (from the research pass)

- SEBI IA Regulations 2013 (verify current text on sebi.gov.in)
- SEBI RA Regulations 2014 + 2024 amendments (verify)
- SEBI 2024 finfluencer circular (verify number)
- DPDP Act 2023 + Rules (verify final notification timeline)
- Anthropic prompt caching docs (verify TTL/discount on docs.anthropic.com)
- NSE archives — `nsearchives.nseindia.com` (verify URL pattern + new bhavcopy format)
- Upstox API v2 docs (broker OAuth path)
- pgvector + HNSW (Postgres docs)
- TimescaleDB Community license (verify post-2024)

> *All "verify" items should be re-checked against live pages before Day 1. The research agents that produced this plan did not have web access; their conclusions are based on their training cutoffs through early 2026.*

---

**Next step:** answer §14, then I cut Day 1 code (repo scaffold + Docker Compose + first migration).
