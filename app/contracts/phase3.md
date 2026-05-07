# Phase 3 — Dev A ⇄ Dev B contract

Single source of truth on the REST + LLM-tool payload shapes that span the
two parallel tracks. Authored by Dev A on day 1; Dev B reviews same day. Any
payload change after this lands needs a PR review by both devs.

## Why this file exists

Phase 3 is split between **Dev A (Data Engine)** and **Dev B (Product Surface)**.
Dev A owns `app/analytics/`, `app/api/`, `app/data/`, `app/db/`, scrape pipelines,
and Alembic migrations. Dev B owns `app/llm/*`, `apps/web/src/*`, the eval suite,
the intent router, and the system prompt. After day 1 Dev B does NOT call into
Dev A's modules directly — only through the REST endpoints below. Dev A does NOT
call any LLM tools.

If a payload shape changes, it lands in **this file in the same PR** that
changes the producer code. Dev B's tools / cards rebase off this contract, not
off implementation details.

## Status

| Endpoint / tool | Spec locked | Stub returning hard-coded JSON | Real implementation |
|-|-|-|-|
| `POST /screener/run` | ✅ | ✅ A-1 | A-2 |
| `GET /screener/list` | ✅ | ✅ A-1 | A-3 |
| `GET /screener/{name}` | ✅ | ✅ A-1 | A-3 |
| `POST /portfolio/import` | ✅ | ✅ A-1 | A-4 |
| `GET /portfolio/{id}/diagnostics` | ✅ | ✅ A-1 | A-5 |
| `POST /backtest/run` | ✅ | ✅ A-1 | A-6 |
| `GET /watchlist` | ✅ | ✅ A-1 | A-7 |
| `POST /watchlist` | ✅ | ✅ A-1 | A-7 |
| `DELETE /watchlist/{ticker}` | ✅ | ✅ A-1 | A-7 |

The stubs let Dev B start B-1 → B-3 against deterministic JSON before Dev A's
real backends land. The shapes do not change between stub and real.

## Conventions

- All numbers that come from the database are returned as **strings** (Decimal
  precision is preserved on the wire — Python `str(Decimal(...))`). Frontend
  parses with `Number(x)`. This matches the existing P2 convention.
- All percentages are 0-100, **not** 0-1.
- Currency values are in INR (₹).
- Timestamps are ISO-8601 (`2026-05-08T10:00:00+00:00`).
- Quarter labels follow the existing FY format (`Q4 FY26`).
- Errors are HTTP 4xx/5xx with `{ "detail": "..." }` (FastAPI default).

---

## REST endpoints (Dev A owns)

### `POST /screener/run`

Run an *expression* OR a *named saved screener* against the universe. Either
`expr` or `name` is required, not both.

**Request**

```json
{
  "expr": "rsi_14 < 30 AND pe_trailing < 20",
  "limit": 50
}
```

OR

```json
{
  "name": "value_rebound",
  "limit": 50
}
```

**Response (200)**

```json
{
  "matched": 7,
  "universe_size": 100,
  "exec_ms": 142,
  "tickers": [
    {
      "symbol": "RELIANCE",
      "score": 0.82,
      "hits": {
        "rsi_14": "28.4",
        "pe_trailing": "18.7",
        "promoter_pct": "50.0000"
      }
    }
  ]
}
```

- `matched`: number of tickers that satisfied the expression.
- `universe_size`: how many tickers were evaluated (NIFTY-100 by default).
- `exec_ms`: end-to-end query latency (server side; for the latency budget
  in P3-B6).
- `tickers[*].score`: a 0..1 ranking score (the screener engine's job; for
  v1 it's just `1.0 - normalised_rank` of the leading metric).
- `tickers[*].hits`: the *exact* values that satisfied each clause of the
  expression — used by the verifier (B-3) and the cards (B-4).

### `GET /screener/list`

Return all stored screeners (seed packs + user-saved).

**Response (200)**

```json
{
  "screeners": [
    {
      "name": "oversold_quality",
      "expr": "rsi_14 < 30 AND pe_trailing < 25 AND promoter_pct > 50",
      "description": "Mean-reversion candidates with healthy fundamentals.",
      "is_seed": true,
      "created_by": null
    }
  ]
}
```

### `GET /screener/{name}`

Return a single stored screener.

**Response (200)** — same shape as one element of `GET /screener/list`'s
`screeners` array.

**Response (404)** if the name is unknown.

### `POST /portfolio/import`

Import a portfolio. Accepts:
- `holdings` — array of `{ticker, quantity, avg_price?}` (CSV-parsed
  client side, or pasted from Zerodha CDSL block).
- `format` — `"csv" | "cdsl_paste"` (informational; server detects).

**Request**

```json
{
  "format": "csv",
  "holdings": [
    {"ticker": "RELIANCE", "quantity": 50, "avg_price": "1380.50"},
    {"ticker": "TCS", "quantity": 10}
  ]
}
```

**Response (200)**

```json
{
  "portfolio_id": 17,
  "n_positions": 12,
  "total_cost_inr": "274350.00"
}
```

Auth: requires a Bearer JWT (PM-1). The portfolio is associated with the
authenticated user; anonymous users get a 401.

### `GET /portfolio/{id}/diagnostics`

Run portfolio diagnostics. The portfolio must belong to the authenticated user.

**Response (200)**

```json
{
  "portfolio_id": 17,
  "as_of": "2026-05-08",
  "n_positions": 12,
  "total_value_inr": "284200.00",
  "concentration": {
    "top_5_pct": "62.4",
    "herfindahl": "0.18"
  },
  "sector_pct": [
    {"sector": "Financial Services", "pct": "38.5"},
    {"sector": "IT", "pct": "22.1"},
    {"sector": "Energy", "pct": "15.0"}
  ],
  "beta_blend": "1.04",
  "div_yield": "1.85",
  "drawdown_1y": "-7.4"
}
```

### `POST /backtest/run`

Replay a single screener over the last `period_days` against `prices_daily`.
**Single-strategy only** in Phase 3 (Decision #5 in the Plan).

**Request**

```json
{
  "name": "value_rebound",
  "period_days": 365
}
```

**Response (200)**

```json
{
  "name": "value_rebound",
  "period_days": 365,
  "n_signals": 47,
  "hit_rate": "0.58",
  "mean_return": "0.063",
  "worst_drawdown": "-0.094",
  "sharpe_proxy": "1.42",
  "equity_curve": [
    {"date": "2025-05-08", "value": "1.0000"},
    {"date": "2025-05-09", "value": "1.0012"}
  ]
}
```

- `equity_curve` is normalised to 1.0 at start; daily mark-to-market.
- `mean_return`, `worst_drawdown`, `hit_rate` are decimals (0.058 = 5.8 %),
  NOT percentages.

### `GET /watchlist`

Return the authenticated user's watchlist.

**Response (200)**

```json
{
  "tickers": ["RELIANCE", "TCS", "INFY"]
}
```

### `POST /watchlist`

Add a ticker.

**Request**

```json
{"ticker": "RELIANCE"}
```

**Response (200)**

```json
{"ok": true, "tickers": ["RELIANCE", "TCS", "INFY"], "size": 3}
```

### `DELETE /watchlist/{ticker}`

Remove a ticker.

**Response (200)**

```json
{"ok": true, "tickers": ["TCS", "INFY"], "size": 2}
```

---

## LLM tools (Dev B owns)

These are NOT REST endpoints — they're function specs registered with OpenAI's
tool-calling API. Dev A does not call them. Each tool is a thin adapter over
the REST endpoints above plus the existing P2 tools (`get_technicals`,
`get_holding`, etc.).

### `run_screener`

```json
{
  "name": "run_screener",
  "description": "Filter the NIFTY-100 universe by an expression OR a saved screener.",
  "parameters": {
    "type": "object",
    "properties": {
      "expr": {"type": "string", "description": "Expression like 'rsi_14 < 30 AND pe_trailing < 20'"},
      "name": {"type": "string", "description": "Name of a saved screener (oversold_quality, value_rebound, ...)"},
      "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}
    }
  }
}
```

Returns: same shape as `POST /screener/run` (Dev B's tool dispatch wraps it).

### `analyse_portfolio`

```json
{
  "name": "analyse_portfolio",
  "description": "Compute concentration / sector / beta / drawdown diagnostics for the user's portfolio.",
  "parameters": {
    "type": "object",
    "properties": {
      "portfolio_id": {"type": "integer"}
    },
    "required": ["portfolio_id"]
  }
}
```

Returns: same shape as `GET /portfolio/{id}/diagnostics`.

### `propose_ideas`

```json
{
  "name": "propose_ideas",
  "description": "Compose screener + technicals + holdings to produce ranked trade ideas tailored to a risk profile.",
  "parameters": {
    "type": "object",
    "properties": {
      "risk_profile": {"type": "string", "enum": ["conservative", "balanced", "aggressive"]},
      "theme": {"type": "string", "description": "Optional theme like 'value rebound' or 'momentum breakout'."},
      "n": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3}
    },
    "required": ["risk_profile"]
  }
}
```

Returns:

```json
{
  "ideas": [
    {
      "ticker": "RELIANCE",
      "thesis": "Oversold (RSI 28) with above-average promoter holding (50%). Setup completes a higher-low at the 200-DMA.",
      "entry": "1430-1450",
      "sl": "1390",
      "target": "1520-1560",
      "score": 0.78,
      "tool_call_ids": ["call_AAA", "call_BBB"]
    }
  ]
}
```

`tool_call_ids` is the auditing seam — every numeric field in `entry/sl/target`
must be reproducible from one of those tool calls. Dev B's verifier (B-3)
enforces this.

### `backtest_screener`

```json
{
  "name": "backtest_screener",
  "description": "Replay a single saved screener over the last N days; return hit rate, mean return, worst drawdown.",
  "parameters": {
    "type": "object",
    "properties": {
      "name": {"type": "string"},
      "period_days": {"type": "integer", "minimum": 30, "maximum": 730, "default": 365}
    },
    "required": ["name"]
  }
}
```

Returns: same shape as `POST /backtest/run` MINUS the `equity_curve` (the LLM
doesn't need 365 daily points; the `BacktestCard` UI fetches the curve
separately).

### `add_to_watchlist`

```json
{
  "name": "add_to_watchlist",
  "description": "Add a ticker to the authenticated user's watchlist.",
  "parameters": {
    "type": "object",
    "properties": {
      "ticker": {"type": "string"}
    },
    "required": ["ticker"]
  }
}
```

Returns: same shape as `POST /watchlist`.

---

## Tool shortlist (extends D8)

Dev B adds these intent → tool mappings to `app/llm/tool_routing.py`:

| Intent | Allowed tools |
|-|-|
| `screener` | `run_screener` |
| `portfolio` | `analyse_portfolio` |
| `idea` | `propose_ideas`, `run_screener`, `get_technicals` |
| `backtest` | `backtest_screener` |

The router (`app/llm/intent.py`) gets corresponding examples for each new intent.

---

## Verifier extension (B-3)

The Phase-2 numeric verifier matches every number-shaped span in the assistant's
final text against tool-call results. For trade-idea outputs (B-3), it must
ALSO match every value inside `entry`, `sl`, `target` — including range bounds
like `"1430-1450"` and percentages like `"+5.2%"`.

If a number in the answer doesn't trace to a `tool_call_id` in the
`propose_ideas` response, the guardrail flags it. Warn-mode: log + audit.
Strict-mode: override message.

---

## Sync cadence

- **Day 1 hand-off:** Dev A commits stub endpoints + this file. Dev B reviews
  and starts B-1 against the stubs.
- **Day 4 mid-phase:** real `/screener/run`, `/screener/list`, `/portfolio/*`
  shapes confirmed live; Dev B card rendering against real data starts.
- **Day 7 final:** end-to-end eval at ≥ 110 / 120; demo recordings.
- **Standup:** 10 min daily. Anything that breaks this contract gets raised
  in standup before code lands.

---

## Versioning

This contract is v1. Breaking changes need:
1. A note at the top of the changed section (`v1 → v2`).
2. The producer-side change in the same PR.
3. A note in the standup channel before merge.

No backwards-compat shims — both devs are on the same `main`, both keep up.
