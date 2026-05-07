# AGENTS.md
> Shared context for all AI coding assistants — Claude Code, Codex, Cursor, Gemini CLI, etc.
> This file is symlinked as CLAUDE.md. One source of truth.

---

## MANDATORY: How Every AI Session Must Work

These rules exist so that switching between Claude, Codex, Cursor, or any other tool mid-feature
causes zero context loss. The **Lark Wiki** is the source of truth for all plans and progress.

### Lark Wiki — Source of Truth

All project documentation lives in the **Lark Wiki** under `Tech Hub > 01 — Clients > Acme > Mr. Market`.
Use the `lark-wiki` skill (via `lark-cli`) to read and write wiki pages. Do NOT maintain separate
local markdown files for plans or progress — the wiki is canonical.

**Wiki structure:**
```
Mr. Market
├── Mr. Market — Overview                  (project summary, vision, competitors)
├── Mr. Market — Architecture & Tech Stack (stack, infra, data architecture)
├── Mr. Market — URLs & Access             (endpoints, API keys, credentials)
├── Mr. Market — Build Plan                (the complete 27-page build plan)
├── Mr. Market — References/               (stable reference docs)
│    ├── Data Strategy                     (scraping, APIs, schedule)
│    ├── Accuracy Strategy                 (5-layer accuracy stack, verification)
│    ├── SEBI Compliance                   (disclaimers, nudge system, risk profiles)
│    └── Database Schema                   (tables, indexes, cache keys)
└── Mr. Market — Updates/                  (active feature work)
     └── <Feature Name>/                  (one folder per active feature)
          ├── Plan                         (phases, decisions, architecture)
          └── Updates                      (current state, progress log)
```

**Wiki page tokens (for lark-cli):**

| Page | obj_token | node_token |
|---|---|---|
| Acme (client) | `NI1MdUob4oTwCRxnGvzlJKhCgrc` | `CB9wwMeHTi7J43kLnVRlJ0ZJgUu` |
| Mr. Market (root) | `FEXgdF5SioBsuwxvwQtlfheJgrb` | `HGcLwdz9tigBGQknoEAll4HFglh` |
| Mr. Market — Overview | `Sy6KdgobAoXXPZxpqwelzqdKghb` | `SZjawX5lNiUND6kFwoelFEuwgIh` |
| Mr. Market — Architecture & Tech Stack | `VUnbdP8FooCAzkx4G7kl8TAqgEj` | `HdKrwlKCGit5EGkcf9zlQYTfgae` |
| Mr. Market — URLs & Access | `HFZidQr9noyomhxpA7ElMhySgRO` | `TKvTwy2y6ip2Znkapx1lUKx4gD8` |
| Mr. Market — Build Plan | `ZZV1dJfceo0D5NxhxYilHTq5g7b` | `BB3DwJ7KEiRb6LkVElGl2Hofgie` |
| Mr. Market — References (parent) | `YVVkdvXiooUcrgxsXXRl8lEAg8c` | `NiCXwzKHJiUal8kqeFtliVYmgcd` |
| Data Strategy | `KiwQdGMcLozEfKxwDP6lJtUWgxc` | `MFdYwZgXBiFIegkMMMilXC4QgLc` |
| Accuracy Strategy | `G7BRdrWAlo3CiGxPsK8lHcJwgBc` | `G1Dmwui3eiNBRDkmANplL2TygAb` |
| SEBI Compliance | `D7DgdHMBlo6Kp7xkeQml1T13gHc` | `OlUTwDckJiLYYgkLq51loTeogZb` |
| Database Schema | `Ouz3daWVIozSOex321Blue6mghc` | `EprewNOwWiaEWOkW06SlhQ7LgOg` |
| Mr. Market — Updates (parent) | `MOwLdr63jovE2lxBg2ulO0ypgQc` | `CE5dwNWFKiD7erkMyJilHarlgEc` |
| Monorepo Scaffold / Plan | `OttVdrrixot1KixmNt4l6PN4ghg` | `XvXDwxHq1ihQRwky1nglVh1GgYc` |
| Monorepo Scaffold / Updates | `JvZMdpTVToEHFUx5QNTlKMJbg1c` | `RHXKwVWJ6iDbp6kalQAls0Bpgmf` |

**Wiki space ID:** `7635896570625396443` (Tech Hub)
**Acme node token:** `CB9wwMeHTi7J43kLnVRlJ0ZJgUu`
**Mr. Market node token:** `HGcLwdz9tigBGQknoEAll4HFglh`

### How to read/write wiki pages

```bash
# Read a page
lark-cli docs +fetch --api-version v2 --doc <obj_token> --doc-format markdown

# Overwrite a page with new content
lark-cli docs +update --api-version v2 --doc <obj_token> --command overwrite --doc-format markdown --content @path/to/file.md

# Append to a page
lark-cli docs +update --api-version v2 --doc <obj_token> --command append --doc-format markdown --content "## New section\n\nContent here"

# Create a new sub-page under a parent node
lark-cli wiki +node-create --space-id 7635896570625396443 --parent-node-token <parent_node_token> --title "Page Title"
```

### At the START of every session
1. Fetch the **Updates** page for the feature you're working on from the wiki
2. Read its **Current State** section — this is where the last AI left off
3. If the user's request doesn't match any existing feature, ask before creating code

### During a session
- If you make an architectural decision that isn't obvious from the code, add it to the **Plan** page's Key Decisions table
- If you hit a blocker, note it in the **Updates** page immediately

### At the END of every session (before stopping)
1. **Overwrite** the **Updates** page with a fresh snapshot of RIGHT NOW
   - What is working
   - What is in progress (be specific: file + function level)
   - What is not started
   - The exact next action for whoever picks this up next
   - Append a progress log entry (date, tool name, what you did)
2. Push the updated content to the wiki using `lark-cli docs +update`

**This is not optional.** If you skip this step, the next AI session starts blind.
Treat updating the wiki as the last action you take in every session.

### When starting a brand-new feature
1. Create a new folder under `Mr. Market — Updates` in the wiki with **Plan** and **Updates** sub-pages
2. Fill in the Plan page before writing any code

---

## What This Project Is

**Mr. Market** is an AI-powered trading assistant designed to be integrated inside the **FinWin app** — a trading platform similar to Zerodha/Groww. It combines technical analysis, fundamental data, news sentiment, and shareholding intelligence into one conversational interface.

Core runtime — tool-calling agent pattern:
1. User sends a query via chat (WebSocket or REST)
2. Intent router classifies the query (stock_price, stock_analysis, why_moving, screener, portfolio, general)
3. LLM orchestrator assembles context and calls relevant tools in parallel
4. Verification pass cross-checks all numeric claims against source data
5. Compliance service injects SEBI disclaimers and risk-profile-aware nudges
6. Response streams back to user

**Core promise:** A retail trader no longer needs to switch between Screener.in, TradingView, Moneycontrol, and Trendlyne. Mr. Market centralizes all of it inside FinWin.

---

## Active Features (Living State)

> Source of truth is in the **Lark Wiki** under `Mr. Market — Updates`. Each feature has a Plan + Updates page.
> Fetch the Updates page at session start to know where things stand.

| Feature | Status | Wiki Plan token | Wiki Updates token |
|---|---|---|---|
| Monorepo Scaffold | done | `OttVdrrixot1KixmNt4l6PN4ghg` | `JvZMdpTVToEHFUx5QNTlKMJbg1c` |
| Phase 1: Informed Bot | not-started | — | — |

---

## Repository Structure

This is a **Python + TypeScript monorepo** with `uv` workspaces (Python) and Vite (frontend):

```
/apps/api          Python FastAPI backend (main API server)
/apps/web          React 18 + Vite + TypeScript chat UI
/workers           Python Celery background jobs (scrapers, pipelines, tasks)
/packages/shared   Shared Python package (DB models, schemas, utils, cache keys)
/infra             Docker Compose, nginx config
/alembic           Database migrations (shared across api + workers)
/scripts           One-off scripts (seed, test scrapers, ingest)
/docs              Architecture, API, compliance docs
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend runtime | Python 3.12+ / FastAPI (async) |
| Frontend | React 18 + Vite + TypeScript |
| State management | Zustand |
| Charts | TradingView Lightweight Charts |
| Database | PostgreSQL + TimescaleDB (time-series) |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Cache | Redis (async via `redis[hiredis]`) |
| Task queue | Celery + Redis broker |
| LLM | Gemini 2.5 Flash (primary) / GPT-5.5 (complex) / Gemini (fallback) |
| Sentiment | FinBERT (HuggingFace transformers, local) |
| TA engine | pandas-ta |
| Vector DB | Qdrant |
| Scraping | BeautifulSoup, nselib, jugaad-data, yfinance |
| Monitoring | Sentry |
| Package manager (Python) | **uv** — never use pip or poetry directly |
| Package manager (JS) | **pnpm** for `apps/web` — never use npm there |
| Containerization | Docker + Docker Compose |

---

## Commands

### API Backend (`/apps/api`)
```bash
uv run uvicorn app.main:create_app --factory --reload --port 8000   # dev server
uv run pytest tests/ -v                                              # run tests
uv run ruff check app/                                               # lint
uv run ruff format app/                                              # format
```

### Frontend (`/apps/web`)
```bash
pnpm run dev          # Vite dev server
pnpm run build        # production build
pnpm run typecheck    # tsc --noEmit
pnpm run lint         # typecheck/lint gate
```

### Workers (`/workers`)
```bash
uv run celery -A app.celery_app worker --loglevel=info               # start worker
uv run celery -A app.celery_app beat --loglevel=info                 # start scheduler
uv run python -m app.scrapers.screener_scraper --ticker RELIANCE     # test a scraper
```

### Database
```bash
alembic upgrade head                   # run migrations
alembic revision --autogenerate -m ""  # create migration
```

### Docker (full stack)
```bash
docker-compose -f infra/docker-compose.yml up -d          # production
docker-compose -f infra/docker-compose.dev.yml up -d       # dev (with hot reload)
docker-compose -f infra/docker-compose.yml logs -f api     # tail API logs
```

---

## Architecture — Key Directories

### Backend (`apps/api/app/`)
```
api/routes/          # HTTP + WebSocket endpoints (chat, analyze, portfolio, health)
services/            # Business logic layer
├── llm_orchestrator.py    # Core agent loop — tool calling, streaming
├── intent_router.py       # Query classification (6 intents)
├── context_builder.py     # Parallel data fetch + assembly
├── verification.py        # Anti-hallucination — cross-check numeric claims
├── compliance.py          # SEBI disclaimers, nudge system, risk gates
└── prompt_templates.py    # Mr. Market persona prompts
tools/               # Agent tools — each is a self-contained callable
├── base.py               # Abstract BaseTool (name, description, execute, to_function_schema)
├── price.py              # get_live_price() — Redis > DB > yfinance fallback
├── technicals.py         # calc_technicals() — pre-computed or pandas-ta on-the-fly
├── fundamentals.py       # get_fundamentals() — from Screener.in data in DB
├── news.py               # fetch_news() — sentiment-tagged headlines
├── holding.py            # get_shareholding() — BSE quarterly data
├── screener.py           # screen_stocks() — SQL against pre-computed table
├── risk_profile.py       # check_risk_profile() — user preferences
└── concall_rag.py        # search_concall() — Qdrant vector search
analytics/           # Computation engines
├── technicals.py         # pandas-ta wrapper (RSI, MACD, BB, SMA, EMA, Pivots, ATR)
├── support_resistance.py # Pivot + Fibonacci S/R detection
├── sentiment.py          # FinBERT wrapper
├── fundamentals.py       # Scorecard computation (P/E, D/E, ROE, ROCE grading)
└── cross_validation.py   # Multi-source confidence scoring
rag/                 # RAG pipeline for annual reports / concall transcripts
core/                # Exceptions, middleware, JWT auth
cache/               # Async Redis wrapper
```

### Workers (`workers/app/`)
```
scrapers/            # Data collection (class-based, all extend BaseScraper)
├── base.py               # BaseScraper contract (fetch, parse, store, health_check)
├── nse_scraper.py        # NSE — FII/DII, live data via nselib
├── bse_scraper.py        # BSE — corporate filings, announcements
├── screener_scraper.py   # Screener.in — fundamentals (P/E, ROE, etc.)
├── yfinance_scraper.py   # Yahoo Finance — OHLCV, fallback prices
├── moneycontrol_scraper.py
├── pulse_scraper.py      # Pulse by Zerodha — RSS news
├── rss_scraper.py        # Google News, ET, Moneycontrol RSS
└── pledge_scraper.py     # Promoter pledge disclosures
pipelines/           # Data processing
├── sentiment.py          # FinBERT batch processing
├── technicals_compute.py # Nightly TA pre-computation for all 500 stocks
└── data_ingestion.py     # Annual report PDF → Qdrant
tasks/               # Celery task definitions
├── nightly_refresh.py    # 4 AM IST — full data refresh
├── news_fetch.py         # Every 15 min during market hours
└── price_streaming.py    # Live price cache updates
```

### Shared Package (`packages/shared/mr_market_shared/`)
```
db/
├── base.py              # SQLAlchemy Base
├── session.py           # SessionManager (async)
└── models/              # All DB models (stock, price, fundamentals, technicals, news, holding, user, conversation)
schemas/             # Shared Pydantic models
utils/               # rate_limiter, retry, user_agents, logger
cache/keys.py        # Redis key patterns + TTLs
constants/           # Stock universe (Nifty 500), enums
```

**Dependency direction (enforced — never break this):**
```
apps/api  ──→  packages/shared  ←──  workers
```
- `packages/shared` is imported by both `apps/api` and `workers`
- `apps/api` and `workers` NEVER import from each other
- `apps/web` communicates with `apps/api` only via HTTP/WebSocket

---

## Design Rules (Non-Negotiable)

1. **Data grounding** — LLM never sees raw user queries without structured data context. Always fetch data first, pass as JSON, instruct "use ONLY this data"
2. **No hallucinated numbers** — Every numeric value in a response must trace back to a source with `fetched_at` timestamp. The `VerificationService` enforces this post-LLM
3. **Anti-block scraping** — All scrapers must use rate limiting, user-agent rotation, and exponential backoff. Respect rate limits: NSE 3 req/sec, BSE 5 req/sec, Screener.in 30 req/min
4. **SEBI compliance** — Every response with price levels gets a disclaimer. Conservative users never receive F&O advice. Nudge system fires on lower circuits, high pledge, insider selling
5. **Class-based architecture** — All scrapers extend `BaseScraper`, all tools extend `BaseTool`. No loose functions for business logic
6. **Shared models only in `packages/shared`** — never define SQLAlchemy models in `apps/api` or `workers`
7. **Async everywhere in API** — all route handlers, DB queries, Redis calls, and HTTP requests must be async
8. **Cache-first reads** — live price from Redis (5s TTL) > DB > external API. Never hit external APIs during user conversations for data that can be pre-fetched
9. **`uv` for Python** — never use pip or poetry. `uv run` for all commands
10. **Type hints required** — all function signatures must have type annotations. Use Pydantic models for all request/response schemas

---

## The 5-Layer Accuracy Stack

This is the core differentiator. Every response passes through all 5 layers:

```
LAYER 5 │ VERIFICATION PASS
        │ Extract claims → match against source → re-prompt if wrong
        │ Drops hallucinations from ~10% → <1%

LAYER 4 │ STRICT GROUNDING
        │ LLM sees ONLY structured JSON, never raw memory
        │ Prompt: "Use ONLY this data, do not invent numbers"

LAYER 3 │ CROSS-VALIDATION
        │ 2-3 sources per data point, voting + confidence

LAYER 2 │ DETERMINISTIC COMPUTATION
        │ Math (RSI, MACD) done by pandas-ta, not LLM

LAYER 1 │ FRESH, TIMESTAMPED DATA
        │ Every value has source + fetched_at + freshness
```

---

## Data Architecture (Two Layers)

**Layer 1: Pre-Computed Screening DB (Updated Nightly)**
- For multi-stock queries: "Show me stocks with RSI < 30 and ROE > 20%"
- Batch job runs at 4 AM IST, pre-computes all indicators for Nifty 500
- Just a SQL filter — no real-time infra needed

**Layer 2: Live Single-Stock Queries (Real-Time During Market Hours)**
- For queries like "What's Reliance trading at?"
- Live price from broker API (Angel One SmartAPI / yfinance for demo)
- Cached in Redis with 5s TTL

---

## Scraping Schedule

| Time | What | Source | Type |
|---|---|---|---|
| Market hours (continuous) | Live price streaming | Broker API | API |
| Market hours (every 15 min) | News RSS + FinBERT tagging | RSS feeds | Scraping |
| 5:00 PM daily | Fundamentals for Nifty 500 | Screener.in | Scraping |
| 6:00 PM daily | FII/DII activity | NSE | Scraping |
| 6:30 PM daily | Bulk/block deals, announcements | BSE | Scraping |
| 7:00 PM daily | OHLCV + pre-compute TA indicators | Broker API | API |
| Quarterly | Shareholding patterns | BSE filings | Scraping |

---

## Redis Cache Keys

| Pattern | TTL |
|---|---|
| `price:{ticker}` | 5 sec |
| `ohlc:{ticker}:{date}` | 24 hr |
| `fundamentals:{ticker}` | 24 hr |
| `technicals:{ticker}` | 1 min |
| `news:{ticker}:latest` | 5 min |
| `sentiment:{ticker}` | 5 min |
| `holding:{ticker}` | 7 days |
| `llm_response:{query_hash}` | 1 hr |
| `scraper:health:{source}` | Persist |

---

## Environment Variables (`.env`)

```
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/mr_market

# Redis
REDIS_URL=redis://localhost:6379/0

# LLM
OPENAI_API_KEY=
GEMINI_API_KEY=
LLM_MODEL=gemini-2.5-flash

# Vector DB
QDRANT_URL=http://localhost:6333

# Broker API (live prices)
ANGEL_ONE_API_KEY=
ANGEL_ONE_CLIENT_ID=

# Auth
JWT_SECRET_KEY=
JWT_ALGORITHM=HS256

# Monitoring
SENTRY_DSN=

# App
DEBUG=true
CORS_ORIGINS=["http://localhost:5173"]
```

---

## Phase Roadmap

| Phase | Name | Weeks | Goal |
|---|---|---|---|
| 1 | "Informed Bot" | 1-4 | Live price, news sentiment, basic company info |
| 2 | "Analyst Bot" | 5-8 | TA engine, entry/exit/SL, shareholding, FII/DII |
| 3 | "Trader Bot" | 9-12 | Multi-stock screener, portfolio review, RAG, nudges |
| 4 | "Portfolio Coach" | 13-24 | Real-time diagnostics, tax harvesting, voice, 50K+ DAU |

---

## Code Conventions

- Python 3.12+ with strict type hints — no `Any` without justification
- Async/await for all I/O (DB, Redis, HTTP, WebSocket)
- Pydantic v2 for all data validation and serialization
- SQLAlchemy 2.0 style (mapped_column, DeclarativeBase)
- Class-based services, tools, scrapers — no loose module-level business logic
- Ruff for linting + formatting (replaces black, isort, flake8)
- React functional components with hooks (no class components)
- Zustand for state management (not Redux)
- TypeScript strict mode in frontend
