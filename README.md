# Mr. Market

AI trading assistant for FinWin (Indian retail trading). **Phase 1 — local demo.**

Plans + progress live in **Lark Wiki** (Tech Hub > 01 — Clients > Acme > Mr. Market). See [`AGENTS.md`](./AGENTS.md) for the wiki token table.

## Layout

```
mr-market/
├── app/                    Python backend (FastAPI + SQLAlchemy 2.0 async)
│   ├── main.py             FastAPI app factory + CORS
│   ├── config.py           pydantic-settings
│   ├── api/                routers
│   │   └── health.py       GET / and GET /healthz
│   └── db/
│       ├── base.py         SQLAlchemy DeclarativeBase
│       ├── session.py      async engine + session factory
│       └── models/         stock, price, news, chat_audit, scrape_log
│
├── apps/web/               React frontend (kept from GitHub origin/main, cleaned)
│   ├── src/
│   │   ├── pages/ChatPage.tsx
│   │   ├── components/{chat,common,home,layout}/
│   │   ├── stores/{chatStore,uiStore}.ts
│   │   ├── hooks/useChat.ts
│   │   ├── services/{api,mockData}.ts
│   │   └── types/index.ts
│   └── vite.config.ts      proxies /api,/healthz,/chat,/quote,/news,/admin → :8001
│
├── data/nifty50.csv        50 NIFTY-50 ticker seed
├── migrations/             Alembic revisions
├── scripts/seed_universe.py
├── alembic.ini
├── pyproject.toml + uv.lock
└── .env.example            copy to .env, fill in ANTHROPIC_API_KEY for D4
```

## One-time setup

```bash
# 1. Services
brew services start postgresql@16
brew services start redis

# 2. Database
/opt/homebrew/opt/postgresql@16/bin/createdb mrmarket

# 3. Backend deps + schema + seed
uv sync
uv run alembic upgrade head
uv run python -m scripts.seed_universe   # 50 NIFTY-50 stocks

# 4. Frontend deps
cd apps/web && pnpm install && cd ../..
```

## Run the stack (two terminals)

```bash
# Terminal 1 — backend on :8001
uv run uvicorn app.main:app --reload --port 8001

# Terminal 2 — frontend on :5174 (proxies to backend)
cd apps/web && pnpm dev
```

Open <http://localhost:5174/>.

## Quick health check

```bash
curl http://localhost:8001/healthz                # direct
curl http://localhost:5174/healthz                # via Vite proxy
psql -d mrmarket -c "SELECT COUNT(*) FROM stocks" # should print 50
```

## What works today (D1)

- Postgres + Redis running natively (Homebrew services)
- 5 tables migrated · 50 NIFTY-50 stocks seeded
- FastAPI on `:8001` with `GET /` and `GET /healthz` (DB roundtrip green)
- React on `:5174` (Tailwind v4, Zustand, React Router) · build clean · dev server proxying to backend
- `/chat` UI streams **mock** responses (real LLM streaming wired in D4)

## Coming next

- **D2:** triangulation engine across nselib + yfinance + Screener + Moneycontrol → real `GET /quote/{ticker}`
- **D3:** news ingestion + sentiment scoring → real `GET /news/{ticker}`
- **D4:** Claude Sonnet tool-calling + SSE streaming → real `/chat`
- **D5:** SEBI guardrails (regex blocklist + ticker→disclaimer + verifier) + audit log
- **D6/D7:** golden eval set ≥48/50, screen-capture backup
