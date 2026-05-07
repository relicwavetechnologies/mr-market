# Mr. Market — Architecture Overview

## System Design

Mr. Market is an AI-powered trading assistant for Indian stock markets, built as a Python + React monorepo with an agent-based architecture.

### Agent-Based Approach

The core LLM orchestrator delegates to specialized tool-calling agents:
- **Fundamental Agent** — retrieves and interprets P/E, ROE, ROCE, D/E, and other financial ratios
- **Technical Agent** — computes RSI, MACD, Bollinger Bands, S/R levels, and trend signals
- **News/Sentiment Agent** — aggregates headlines from multiple sources and runs FinBERT sentiment classification
- **Holdings Agent** — tracks FII/DII/promoter shareholding changes quarter-over-quarter
- **Compliance Agent** — gates all outputs through SEBI disclaimer and risk profile validation

### Two-Layer Data Architecture

1. **Hot Layer (Redis)** — intraday prices, cached API responses, rate-limit counters, and session state. TTL-driven expiry ensures freshness.
2. **Cold Layer (PostgreSQL + Qdrant)** — historical OHLCV data, fundamental snapshots, shareholding patterns, news archives, and vector-embedded annual reports for RAG retrieval.

### Five-Layer Accuracy Stack

1. **Multi-Source Cross-Validation** — every data point is scraped from at least two independent sources (Screener, MoneyControl, NSE, BSE, Yahoo Finance) and reconciled.
2. **Confidence Scoring** — each response carries a confidence level (HIGH / MEDIUM / LOW) based on source agreement and data freshness.
3. **Temporal Awareness** — the system knows market hours, corporate action dates, and result seasons to contextualise data appropriately.
4. **Contradiction Detection** — when sources disagree beyond a threshold, the system flags the discrepancy rather than picking one.
5. **Human-Readable Sourcing** — every claim is attributed to a verifiable source with timestamps.

## Monorepo Structure

```
apps/api/          FastAPI backend — REST + WebSocket chat
apps/web/          React + Vite frontend — chat UI, charts, scorecards
workers/           Celery workers — scrapers, data pipelines, scheduling
packages/shared/   Shared SQLAlchemy models, Pydantic schemas, utilities
infra/             Docker Compose, nginx config
alembic/           Database migrations
scripts/           CLI utilities for seeding, testing, ingestion
```

## Tech Stack

| Layer       | Technology                                    |
|-------------|-----------------------------------------------|
| Frontend    | React 19, Vite, TypeScript, TailwindCSS, Zustand |
| Backend     | FastAPI, WebSockets, Pydantic v2              |
| LLM         | Google Gemini 2.5 Flash (primary), OpenAI (fallback) |
| Workers     | Celery + Redis (broker & result backend)      |
| Database    | PostgreSQL 16 (via SQLAlchemy 2.0 async)      |
| Vector DB   | Qdrant (annual report embeddings for RAG)     |
| Cache       | Redis 7                                       |
| Proxy       | nginx                                         |
| Containers  | Docker Compose                                |
