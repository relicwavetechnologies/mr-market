# AGENTS.md
> Shared context for all AI coding assistants — Claude Code, Codex, Cursor, Gemini CLI, etc.
> This file is symlinked as CLAUDE.md. One source of truth.

---

## MANDATORY: How Every AI Session Must Work

These rules exist so that switching between Claude, Codex, Cursor, or any other tool mid-feature causes zero context loss. The **Lark Wiki** is the source of truth for all plans and progress.

### Lark Wiki — Source of Truth

All project documentation lives in the **Lark Wiki** under `Tech Hub > 01 — Clients > Acme > Mr. Market`. Use `lark-cli` to read and write wiki pages. Do NOT maintain separate local markdown files for plans or progress — the wiki is canonical.

**Wiki structure:**
```
Mr. Market  (node: HGcLwdz9tigBGQknoEAll4HFglh)
├── Mr. Market — Overview
├── Mr. Market — Architecture & Tech Stack
├── Mr. Market — URLs & Access
├── Mr. Market — Build Plan                    ← top-level project plan (current = demo plan)
├── Mr. Market — References/   (stable reference docs)
│    ├── Data Strategy
│    ├── Accuracy Strategy
│    ├── SEBI Compliance
│    └── Database Schema
└── Mr. Market — Updates/      (active feature work)
     ├── Monorepo Scaffold     (legacy)
     └── Phase 1 — Local Demo  ← active feature
          ├── Plan
          └── Updates
```

**Wiki space ID:** `7635896570625396443` (Tech Hub)
**Project node token:** `HGcLwdz9tigBGQknoEAll4HFglh`
**GitHub origin:** `https://github.com/relicwavetechnologies/mr-market.git` — only `apps/web/` was kept from origin/main; backend is our own.

**Wiki page tokens (for lark-cli):**

| Page | node_token | obj_token |
|---|---|---|
| Mr. Market (project) | `HGcLwdz9tigBGQknoEAll4HFglh` | — |
| Overview | `SZjawX5lNiUND6kFwoelFEuwgIh` | `Sy6KdgobAoXXPZxpqwelzqdKghb` |
| Architecture & Tech Stack | `HdKrwlKCGit5EGkcf9zlQYTfgae` | `VUnbdP8FooCAzkx4G7kl8TAqgEj` |
| URLs & Access | `TKvTwy2y6ip2Znkapx1lUKx4gD8` | `HFZidQr9noyomhxpA7ElMhySgRO` |
| **Build Plan** (top-level) | `BB3DwJ7KEiRb6LkVElGl2Hofgie` | `ZZV1dJfceo0D5NxhxYilHTq5g7b` |
| References (parent) | `NiCXwzKHJiUal8kqeFtliVYmgcd` | `YVVkdvXiooUcrgxsXXRl8lEAg8c` |
| References → Data Strategy | `MFdYwZgXBiFIegkMMMilXC4QgLc` | `KiwQdGMcLozEfKxwDP6lJtUWgxc` |
| References → Accuracy Strategy | `G1Dmwui3eiNBRDkmANplL2TygAb` | `G7BRdrWAlo3CiGxPsK8lHcJwgBc` |
| References → SEBI Compliance | `OlUTwDckJiLYYgkLq51loTeogZb` | `D7DgdHMBlo6Kp7xkeQml1T13gHc` |
| References → Database Schema | `EprewNOwWiaEWOkW06SlhQ7LgOg` | `Ouz3daWVIozSOex321Blue6mghc` |
| Updates (parent) | `CE5dwNWFKiD7erkMyJilHarlgEc` | `MOwLdr63jovE2lxBg2ulO0ypgQc` |
| Updates → Monorepo Scaffold (legacy) | `R1ZlwUpVnijxxqkifxDlQwpIgjf` | `FHCtdb9A6o8QjrxFiw5lVTAHgad` |
| Updates → **Phase 1 — Local Demo** (folder) | `Gngcw4bzziv3hckWAi8ltkbmg9d` | `NBEId2Zpuo2dPexbmB1llBFfgsb` |
| Phase 1 → **Plan** (canonical demo plan) | `OMhtwb622iXEHfkhsE9lcznVgCe` | `R4xvdN4PFoNSfnxfQ5nlgn5ygab` |
| Phase 1 → **Updates** (current state + progress log) | `AHWewTiAEiLoGgkuPROlSKOfg9f` | `CzsRdi32zokbDExSnXxlXhRYgLe` |

**Active feature:** `Phase 1 — Local Demo` (Updates obj_token `CzsRdi32zokbDExSnXxlXhRYgLe`)

### How to read/write wiki pages

```bash
# Read a page
lark-cli docs +fetch --api-version v2 --doc <obj_token> --doc-format markdown

# Overwrite a page (relative path required)
lark-cli docs +update --api-version v2 --doc <obj_token> --command overwrite --doc-format markdown --content @.context/file.md

# Append to a page
lark-cli docs +update --api-version v2 --doc <obj_token> --command append --doc-format markdown --content "content"

# Create a new sub-page
lark-cli wiki +node-create --space-id 7635896570625396443 --parent-node-token <PARENT_NODE> --title "Title"
```

### At the START of every session
1. Fetch the **active feature's Updates page** (`CzsRdi32zokbDExSnXxlXhRYgLe`).
2. Read its **Current State** — this is where the last session left off.
3. If the request doesn't match an existing feature, ask before creating code.

### During a session
- Architecture decisions → the feature's **Plan** page (Key Decisions table).
- Blockers → the feature's **Updates** page immediately.

### At the END of every session (before stopping)
1. Overwrite the active feature's **Updates** page with a fresh snapshot:
   - What is working
   - What is in progress (file + function level)
   - What is not started
   - Blockers
   - Exact next action
   - Append a progress log entry (date, tool, what you did)
2. Push via `lark-cli docs +update --api-version v2 --doc CzsRdi32zokbDExSnXxlXhRYgLe --command overwrite --doc-format markdown --content @.context/updates-snapshot.md`

**This is not optional.** Treat updating the wiki as the last action in every session.

### When starting a brand-new feature
1. Create a folder under `Mr. Market — Updates` (parent node `CE5dwNWFKiD7erkMyJilHarlgEc`) with **Plan** and **Updates** sub-pages.
2. Fill in the Plan before writing code.
3. Add the new tokens to the table above.

---

## Project Snapshot — Mr. Market

**What it is:** AI trading assistant for FinWin (Indian retail trading app). Pay for intelligence (LLM), don't pay for data (scrape it). Goal: surface accurate stock info and refuse anything that crosses SEBI advice line.

**Active phase:** **Phase 1 — Local Demo** (~7 days). Runs on user's Mac, free data sources only, accuracy ≥99%, no VPS, no DPDP/broker-OAuth yet.

**Stack (locked for demo):**
- **Backend:** Python 3.12 + uv + FastAPI 0.115 + uvicorn + httpx + curl_cffi + arq + Anthropic SDK · runs on `:8001`
- **DB:** Postgres 16 (Homebrew, native — no Docker) · database `mrmarket`
- **Cache:** Redis 7 (Homebrew)
- **LLM:** Claude Sonnet 4.5+ (workhorse, 1h prompt cache), Claude Haiku 4.5 (intent router)
- **Sentiment:** `mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis` (CPU)
- **Frontend:** Vite + React 19 + TypeScript + Tailwind v4 + Zustand + lucide-react · runs on `:5174` (lives at `apps/web/`, kept from GitHub origin)
- **Data sources (all free):** nselib, yfinance, NSE archives (`nsearchives.nseindia.com`), Screener.in scrape, Moneycontrol scrape, Pulse RSS, Moneycontrol/ET/Mint/BS RSS, GDELT 2.0 (BigQuery)

**Headline rule:** Triangulate every number across ≥3 free sources. Refusing is better than being wrong. Verifier matches every numeric claim in LLM output against tool-call JSON.

**SEBI safe-harbor pattern:** No buy/sell/hold/target language. Hard regex blocklist on output. Ticker→disclaimer auto-injector. Audit log every prompt/response.

---

## Run book (local dev)

```bash
# 1. Postgres + Redis (Homebrew, run as services)
brew services start postgresql@16
brew services start redis

# 2. One-time DB bring-up
/opt/homebrew/opt/postgresql@16/bin/createdb mrmarket
uv sync
uv run alembic upgrade head
uv run python -m scripts.seed_universe

# 3. Backend (terminal 1) — :8001
uv run uvicorn app.main:app --reload --port 8001

# 4. Frontend (terminal 2) — :5174
cd apps/web && pnpm install && pnpm dev
```

Open <http://localhost:5174/>. Health check: `curl http://localhost:5174/healthz` (proxies through Vite to backend).

---

## Open questions (waiting on user)

1. Universe size — top 50 (faster) or top 200?
2. LLM provider lock — Claude Sonnet 4.5+ (~₹200 demo budget) or Gemini Flash free tier?
3. Demo audience — investors / FinWin team / co-founder?
4. Demo deadline — fixes whether 7-day sprint or relaxed.

---

## Cleanup note

A stray `FinWin` client folder was created at `Tech Hub > 01 — Clients > FinWin` during the wiki bootstrap. Delete it manually in Lark UI when convenient — `lark-cli` does not expose `wiki node-delete`. The canonical home is **Acme > Mr. Market**.
