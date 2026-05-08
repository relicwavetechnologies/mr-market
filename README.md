# Midas

AI trading assistant for FinWin (Indian retail trading). **Phase 1 — local demo.**

Plans + progress live in **Lark Wiki**. See [`AGENTS.md`](./AGENTS.md) for the wiki token table.

## Layout

```
midas/
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
│   └── vite.config.ts      proxies /api,/healthz,/chat,/quote,/news,/admin → :8000
│
├── data/nifty50.csv        50 NIFTY-50 ticker seed
├── migrations/             Alembic revisions
├── scripts/seed_universe.py
├── alembic.ini
├── pyproject.toml + uv.lock
└── .env.example            copy to .env, fill in OPENAI_API_KEY (or use codex login)
```

## One-time setup

### OpenAI auth (pick one)

The backend resolves credentials in this order on every request:
**Redis (paste-key) → `OPENAI_API_KEY` env → `~/.codex/auth.json`**.

| Path | Best for | How |
|---|---|---|
| **Codex login** (recommended) | Anyone with a ChatGPT Plus / Pro / Team subscription | `npm i -g @openai/codex` then `codex login` — opens a browser, signs in with your ChatGPT account, writes credentials to `~/.codex/auth.json`. The server picks them up automatically; refreshes are also picked up live. |
| `.env` | Classic API-key billing | Edit `.env`: `OPENAI_API_KEY=sk-...` and restart the backend. |
| Web paste | Quick demo / temporary | Open the chat page, click "paste key" in the auth banner, paste — stored in Redis with a 24h TTL. |

`/auth/openai/status` exposes the active source so you can verify; the `AuthBanner` in the React UI does this automatically on every page load.

### Local infra

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
# Terminal 1 — backend on :8000
uv run uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend on :5174 (proxies to backend)
cd apps/web && pnpm dev
```

Open <http://localhost:5174/>.

## Quick health check

```bash
curl http://localhost:8000/healthz                # direct
curl http://localhost:5174/healthz                # via Vite proxy
psql -d mrmarket -c "SELECT COUNT(*) FROM stocks" # should print 50
```

## What works today (D1)

- Postgres + Redis running natively (Homebrew services)
- 5 tables migrated · 50 NIFTY-50 stocks seeded
- FastAPI on `:8000` with `GET /` and `GET /healthz` (DB roundtrip green)
- React on `:5174` (Tailwind v4, Zustand, React Router) · build clean · dev server proxying to backend
- `/chat` UI streams **mock** responses (real LLM streaming wired in D4)

## Coming next

- **D2:** triangulation engine across nselib + yfinance + Screener + Moneycontrol → real `GET /quote/{ticker}`
- **D3:** news ingestion + sentiment scoring → real `GET /news/{ticker}`
- **D4:** Claude Sonnet tool-calling + SSE streaming → real `/chat`
- **D5:** SEBI guardrails (regex blocklist + ticker→disclaimer + verifier) + audit log
- **D6/D7:** golden eval set ≥48/50, screen-capture backup
