# Mr. Market — Strategy, Competitor Analysis & Implementation Plan

**Prepared for:** Raman Sir Demo | **Prepared by:** FinWin Team  
**Date:** May 2026 | **Status:** Working Draft

---

## 1. What Mr. Market Is

An AI-powered trading assistant designed to be integrated inside the **FinWin app** — a trading platform similar to Zerodha/Groww. Mr. Market is not a support bot — it's a **trading companion** that combines technical analysis, fundamental data, news sentiment, and shareholding intelligence into one conversational interface.

**Platform:** FinWin (Trading App similar to Zerodha/Groww)  
**Integration:** Mr. Market lives inside FinWin as a built-in chatbot. Not a standalone product.  
**Target Users:** Retail traders (intraday & long-term) and investors using the FinWin app.

**Core promise:** A retail trader no longer needs to switch between Screener.in, TradingView, Moneycontrol, and Trendlyne. Mr. Market centralizes all of it inside FinWin.

**Example interactions:**

> **User:** "Should I buy Adani Power now?"  
> **Mr. Market:** "Momentum is high, but RSI is over 80 (Overbought). A pullback is likely. If you're aggressive, watch for a break above ₹750. Conservative? Wait for a dip to ₹720."

> **User:** "Why is Tata Motors falling?"  
> **Mr. Market:** "Tata Motors is down 2% primarily due to JLR sales numbers missing estimates released 30 mins ago. Also, the overall Auto index is weak (-1.5%) today."

---

## 2. Competitor Landscape

### 2.1 Direct Competitors (India-Specific)

| Platform | What It Does | Strengths | Weaknesses | Pricing |
|----------|-------------|-----------|------------|---------|
| **Jarvis Invest** | SEBI-registered AI advisor, stock recommendations, sentiment tracker | Real-time OI/sentiment signals, FII/DII tracking, SEBI registered, partnered with 32+ brokerages | Black-box recommendations — no conversational interface, users can't ask "why", no TA module with specific levels | Paid plans (₹999+/mo) |
| **Trendlyne** | Stock analytics, DVM scoring (Durability, Valuation, Momentum), NLP-based earnings summaries | DVM score is well-respected, deep screeners, real-time alerts, portfolio tracking | Not conversational, no trade setup suggestions, no entry/exit/stop-loss logic | Freemium (Pro ₹500+/mo) |
| **StockEdge** | Mobile-first stock scanning, 15+ auto-detected chart patterns (triangles, breakouts, H&S) | Auto pattern scans, daily market summary, pre-built technical scans, sector analysis | App-only, no AI chat, no fundamental scoring engine, no specific entry/exit levels | Freemium (Club ₹999/mo) |
| **Tickertape** | Stock screening, investment checklist, Market Mood Index (Fear vs Greed) | Cleanest UI in the market, beginner-friendly, good peer comparisons, hygiene checklist | No AI recommendations, no TA module, no conversational interface | Freemium |
| **Screener.in** | Fundamental screening, custom query builder, 10+ years financial history | Most powerful free fundamental tool in India, custom query language, deep financial data | No AI layer, no technicals, no news, no chat — purely manual research tool | Free (Premium ₹4,500/yr) |
| **Stoxra** | AI mentor + charting + option chain + paper trading | Free tier is generous, AI explains chart setups, OI/PCR/max pain data | Newer platform, limited track record, no fundamental depth | Free |
| **Zerodha Streak** | No-code algo strategy builder + backtesting | Integrated with Zerodha, visual strategy builder, live deployment | No AI chat, no fundamental analysis, locked to Zerodha users only | Free with Zerodha |

### 2.2 Global Competitors (For Reference)

| Platform | Notable Feature | Why It Matters for Us |
|----------|----------------|----------------------|
| **Trade Ideas (Holly AI)** | 5-8 daily AI trade ideas with entry/exit/SL + confidence levels | Closest to what Mr. Market aims to do — but US-only, $167/mo. Proves the model works. |
| **TrendSpider** | Automated trendline detection + multi-timeframe analysis | Smart charting approach — we can learn from their TA automation |
| **TradeEasy.ai** | News sentiment engine — Bullish/Bearish/Neutral per article with impact scoring | Their sentiment model architecture is exactly what our News Engine should replicate |
| **Tickeron** | AI pattern recognition + confidence scores + public track records on AI "robots" | Transparency in AI — showing "why" behind each call. Mr. Market should do this too. |

### 2.3 Where Mr. Market Wins — The Key Differentiator

**No existing Indian platform combines ALL of these in a conversational interface:**

1. ✅ Conversational AI (ask in natural language, get trade setups)
2. ✅ Technical Analysis with specific entry/exit/SL levels
3. ✅ Fundamental scorecard (P/E, D/E, ROE, ROCE)
4. ✅ News sentiment correlation with price movement
5. ✅ Shareholding intelligence (promoter pledge alerts, FII/DII flows)
6. ✅ SEBI compliance baked in (disclaimers, risk profiling, nudges)
7. ✅ Integrated inside a trading app (not a standalone tool)

**Jarvis comes closest** but is a black-box recommendation engine — users can't have a conversation or ask "why did you recommend this?". **Trendlyne has depth** but no conversational interface. **StockEdge has pattern scans** but no AI reasoning or fundamental scoring.

**The pitch in one line:** "Every existing tool gives you one piece of the puzzle. Mr. Market gives you the complete picture in one conversation."

### Differentiator Comparison Table

| Feature | Jarvis | Trendlyne | StockEdge | Screener.in | Mr. Market |
|---------|--------|-----------|-----------|-------------|------------|
| Conversational AI | ❌ | ❌ | ❌ | ❌ | ✅ |
| Specific Entry/Exit/SL | ❌ (black box) | ❌ | ❌ | ❌ | ✅ |
| News → Price Correlation | ❌ | Partial | ❌ | ❌ | ✅ |
| Fundamental Scorecard | ❌ | ✅ | Partial | ✅ (manual) | ✅ |
| Shareholding Alerts | ❌ | ✅ | Partial | ❌ | ✅ |
| Risk Profile Aware | ✅ | ❌ | ❌ | ❌ | ✅ |
| SEBI Guardrails | ✅ (registered) | N/A | N/A | N/A | ✅ (built-in) |
| Integrated in Trading App | ❌ (standalone) | ❌ | ❌ | ❌ | ✅ (inside FinWin) |

---

## 3. Data Strategy — Scraping, APIs & Architecture

### 3.1 The Two-Layer Data Architecture

Mr. Market's data needs fall into two very different layers:

**Layer 1: Pre-Computed Screening Database (Updated Nightly)**  
For multi-stock queries like "Show me stocks with RSI < 30 and ROE > 20%". This doesn't need real-time data. Daily RSI is calculated from daily closing prices — it only changes once a day. ROE is quarterly. So this query is essentially a database filter against pre-computed values. Runs against nightly batch data.

**Layer 2: Live Single-Stock Queries (Real-Time During Market Hours)**  
For queries like "What's Reliance trading at?" or "Give me a trade setup for HDFC Bank". These need the current price to say "it's near support at ₹1,580" rather than using yesterday's close. This comes from broker API streaming (not scraping).

This separation simplifies the architecture massively — the screening feature needs zero real-time infrastructure, just a good nightly batch job.

### 3.2 What We Scrape (Web Scraping)

Web scraping covers data from sites that don't offer official APIs. Here's what, from where, and how often:

**Fundamental Data — Screener.in**
- **What:** P/E ratio, D/E ratio, ROE, ROCE, quarterly revenue growth, profit margins, industry comparisons
- **How often:** Once daily, post-market (after 6 PM). Fundamentals don't change intraday. Even Screener.in itself updates after market hours. Honestly, even weekly would work for most metrics — daily just catches newly published quarterly results faster.
- **Scope:** Start with Nifty 500 stocks (covers 95% of what retail traders ask about). Expand to small/micro caps only when user demand warrants it.
- **Method:** BeautifulSoup/Selenium custom scraper, or Apify actors that already exist for Screener.in (₹0.90 per 1000 results on Apify).
- **Storage:** Scrape → store in PostgreSQL. The bot queries our DB, never hits Screener.in during a user conversation.
- **Legal:** Publicly visible data, acceptable for internal analysis. Do NOT redistribute raw scraped data commercially. Use rate limiting, respectful crawling.

**BSE/NSE Filings & Announcements**
- **Shareholding patterns:** Quarterly (BSE publishes structured data). Scrape when BSE publishes new quarterly filings.
- **Corporate announcements:** Board meetings, dividends, stock splits, bonus issues. Check 2-3 times daily (pre-market, lunch, post-market).
- **Bulk/block deals:** Daily, post-market from BSE.
- **Insider trading (SAST disclosures):** Daily from BSE.
- **Legal:** All public domain data. BSE/NSE filings are freely usable.

**FII/DII Activity Data**
- **Source:** NSE website (published daily after 6 PM)
- **How often:** Once daily, after 6 PM
- **What:** Net buy/sell by FIIs and DIIs — critical for understanding institutional sentiment

**News Feeds**
- **Sources:** Google News RSS, Moneycontrol RSS, Economic Times RSS — filtered by stock ticker names
- **How often:** Every 10-15 minutes during market hours (9:15 AM - 3:30 PM). News drives intraday moves, so this is the most frequent scrape.
- **Processing:** Each headline runs through FinBERT (financial sentiment model) for Bullish/Bearish/Neutral tagging
- **Storage:** Store headline + sentiment score + timestamp + linked ticker symbols. We don't need full article text — just headlines and sentiment.
- **Legal:** Standard RSS usage is fine. Don't reproduce full articles — only summaries and sentiment tags.

### 3.3 What We DON'T Scrape (Licensed API Data)

**Live Market Prices — This CANNOT be scraped.**  
NSE explicitly prohibits scraping live prices and actively blocks IPs. This must come from a licensed source. Options:

| Provider | Cost | What You Get | Best For |
|----------|------|-------------|----------|
| **Angel One SmartAPI** | **₹0** (free with account) | WebSocket streaming, live quotes, historical OHLCV, order placement | **Demo & MVP — best free option** |
| **Dhan API** | **₹0** (free with account) | Similar to Angel One — live data, historical, orders | Alternative free option |
| **Upstox API** | **₹0** (free with account) | Live streaming, historical data | Another free alternative |
| **Kite Connect (Zerodha)** | **₹2,000/mo** | Most mature API, reliable WebSocket, best documentation | Production (when scaling) |
| **TrueData** | **₹1,500+/mo** | Exchange-licensed L1 data at 1-sec frequency | Production (if broker-agnostic) |
| **yfinance (Python)** | **₹0** | 15-minute delayed quotes for Indian stocks | **Quick demo hack — good enough** |

**For demo:** Use `yfinance` (zero setup, one line of Python) or Angel One SmartAPI (free, but needs account KYC). The 15-minute delay from yfinance doesn't matter in a demo — nobody will cross-check.

**Historical OHLCV (for technical indicator calculation)**
- Same source as live prices — broker API or `yfinance`
- Fetch daily candles once post-market
- Store in PostgreSQL (or TimescaleDB at scale)
- `pandas_ta` library calculates RSI, MACD, moving averages, pivot points on-the-fly from this stored data

### 3.4 Scraping Schedule Summary

| Time | What Runs | Source | Type |
|------|-----------|--------|------|
| Market hours (continuous) | Live price streaming | Broker API (Angel One/Kite) | API subscription (NOT scraping) |
| Market hours (every 15 min) | News RSS fetch + FinBERT sentiment tagging | Google News, Moneycontrol, ET RSS | Lightweight scraping |
| 5:00 PM daily | Fundamental data for Nifty 500 | Screener.in | Web scraping |
| 6:00 PM daily | FII/DII activity data | NSE website | Web scraping |
| 6:30 PM daily | Bulk/block deals, insider trades, announcements | BSE website | Web scraping |
| 7:00 PM daily | Historical OHLCV update + pre-compute RSI/MACD/MAs for all 500 stocks | Broker API | API call |
| Quarterly (when published) | Shareholding patterns | BSE filings | Web scraping |

### 3.5 One-Time Backfill vs Daily Incremental

**First-time setup (one-time, takes a few hours):**
- Scrape Screener.in for all 500 stocks — full financial history
- Download 1-2 years of daily OHLCV candle data for all 500 stocks
- Fetch last 4 quarters of shareholding patterns from BSE
- Build initial news sentiment archive (past 30 days)
- Pre-compute technical indicators (RSI, MACD, MAs, pivots) for all 500 stocks

**After that, daily incremental updates are tiny:**
- ~500 Screener.in page refreshes (takes 20-30 min with rate limiting)
- One FII/DII page from NSE
- One BSE announcements page
- ~50-100 news headlines via RSS
- 500 OHLCV candle updates

The heavy lifting is the backfill. After that, the daily job is lightweight.

---

## 4. Technical Architecture

### 4.1 Agent-Based Approach (Recommended over Monolithic RAG)

Instead of building a single RAG pipeline, build Mr. Market as a **tool-using AI agent**. The LLM acts as the orchestrator and calls specific tools based on what the user asks:

```
User Query → Intent Classifier → AI Agent (LLM) → Tool Calls → Response
                                       ↓
                              ┌────────────────────┐
                              │   Available Tools    │
                              ├────────────────────┤
                              │ get_live_price()     │  ← Broker API
                              │ calc_technicals()    │  ← pandas_ta on stored OHLCV
                              │ fetch_news()         │  ← Pre-fetched news DB
                              │ get_fundamentals()   │  ← Pre-scraped Screener data
                              │ get_shareholding()   │  ← Pre-scraped BSE data
                              │ screen_stocks()      │  ← Query pre-computed DB
                              │ check_risk_profile() │  ← User profile DB
                              │ add_disclaimer()     │  ← SEBI compliance
                              └────────────────────┘
```

**Why agent-based over pure RAG:**
- Each module is independent and testable
- LLM decides which tools to call based on the query (ask about news → calls fetch_news, ask about TA → calls calc_technicals)
- Easy to add new tools later (options chain in Phase 3, portfolio review, etc.)
- Claude's tool-use API or OpenAI function calling makes this straightforward
- The bot only hits the data it needs per query — not everything every time

### 4.2 Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **LLM** | Claude API (Sonnet) or GPT-4o | Tool-use support, fast, cost-effective. Don't fine-tune for MVP — intelligence comes from data, not model tuning. |
| **Backend** | Python + FastAPI | Async-native, WebSocket support, great for financial compute |
| **TA Engine** | `pandas_ta` library | RSI, MACD, Bollinger Bands, Pivot Points, ATR — all built-in |
| **Sentiment** | FinBERT (HuggingFace) | Financial-domain-specific BERT model for news sentiment |
| **Vector DB** | ChromaDB (MVP) → Pinecone (scale) | For annual reports, conference call transcripts (Phase 3) |
| **Cache** | Redis | Cache live prices, reduce API calls during market hours |
| **Database** | PostgreSQL | User profiles, risk preferences, all scraped fundamental/technical data |
| **Frontend Chat** | React + WebSocket | Streaming responses, embed inside FinWin app |
| **Charts** | TradingView Lightweight Charts | Embed interactive charts in bot responses |
| **Scraping** | BeautifulSoup + custom Python scripts (or Apify) | Screener.in, BSE filings, news RSS |

---

## 5. Core Modules (from FRD)

### 5.1 News & Sentiment Engine
- Fetch latest news for a ticker from RSS feeds
- Run FinBERT sentiment analysis (Positive/Negative/Neutral)
- Cross-check global indices (if NASDAQ down → IT stocks correlation)
- Output: "Tata Motors is down 2% primarily due to JLR sales numbers missing estimates released 30 mins ago. Auto index is weak (-1.5%) today."

### 5.2 Technical Analysis Module
- Calculates: 50 DMA, 200 DMA, RSI, MACD, Pivot Points, Fibonacci Retracements, ATR
- Mandatory response structure for every trade setup:
  - Current Trend: Bullish/Bearish/Sideways
  - Immediate Support: ₹X
  - Immediate Resistance: ₹Y
  - Stop Loss Suggestion: ₹Z (with reasoning — "below recent swing low" or "1.5x ATR")
  - Disclaimer: Always appended

### 5.3 Fundamental Analysis Module
- Data points: P/E vs Industry P/E, D/E Ratio, ROE, ROCE, Quarterly Revenue Growth (YoY)
- Output format: Scorecard — "ITC looks healthy: High Dividend Yield (3%), Debt-free, ROE of 25%. However, revenue growth slowed to 4% this quarter."

### 5.4 Shareholding Intelligence
- Promoter pledge check: Alert if >10% shares pledged (red flag)
- FII/DII flows: Quarter-over-quarter stake changes
- Insider trading: Flag recent promoter buys/sells
- Output: "Promoters: 0% (Professional Mgmt), FIIs: 55% (High interest), DIIs: 12%, Retail: 33%"

### 5.5 Multi-Stock Screening (Phase 3)
- Queries like: "Show me stocks with RSI < 30 and ROE > 20%"
- Runs against pre-computed nightly database — NO real-time data needed
- Daily RSI uses daily closing prices (changes once/day), ROE is quarterly
- Implementation: SQL query on pre-computed screening table

---

## 6. SEBI Regulatory Compliance

### 6.1 The "Advisor" Guardrail
- If bot gives specific price levels ("Buy at ₹100"), SEBI may classify it as Investment Advisory
- Solution: **Disclaimer injection** on every response with price levels: "Generated by AI based on technical parameters. Consult a SEBI registered advisor."
- Implemented both in LLM system prompt AND as a post-processing enforcement step

### 6.2 Risk Profile Check
- Before first trade suggestion, bot asks: "Are you a high-risk trader or a conservative investor?"
- 5-6 onboarding questions (investment horizon, loss tolerance, F&O experience)
- Stored as user attribute — agent checks profile before generating responses
- Conservative users: Bot refuses F&O advice entirely

### 6.3 Nudge System
- Pre-trade safety checks triggered when user mentions buying a stock:
  - Lower circuit status → "⚠️ This stock is hitting lower circuit. You cannot sell if you buy today."
  - Promoter pledge >10% → Red flag warning
  - SEBI actions/surveillance → Warning before proceeding

### 6.4 Open Question
- For MVP: Does the disclaimer model suffice, or do we need SEBI RA/IA registration?
- Jarvis Invest is SEBI-registered — gives them credibility. Worth considering for FinWin long-term.

---

## 7. MVP Roadmap (12 Weeks)

### Phase 1: "The Informed Bot" — Weeks 1–4
- [ ] Integrate live price API (Angel One SmartAPI — free)
- [ ] News feed aggregation (RSS) + FinBERT sentiment tagging
- [ ] Basic company info (sector, P/E, market cap) via Screener.in scraping
- [ ] One-time backfill of Nifty 500 stock data
- [ ] Simple conversational interface (Streamlit for internal → React for prod)
- [ ] Risk profile onboarding flow
- **Demo-able:** "What is the price of Reliance?" / "Why is TCS falling?"

### Phase 2: "The Analyst Bot" — Weeks 5–8
- [ ] Technical Analysis engine (pandas_ta — RSI, MACD, MAs, Pivots, ATR)
- [ ] Entry/Exit/Stop-Loss calculation logic
- [ ] Nightly batch job: pre-compute all indicators for 500 stocks
- [ ] Shareholding pattern integration (BSE quarterly data)
- [ ] FII/DII flow tracking (NSE daily scrape)
- [ ] Promoter pledge alerts
- **Demo-able:** "Give me a trade setup for HDFC Bank" / "Who owns Zomato?"

### Phase 3: "The Trader Bot" — Weeks 9–12
- [ ] Multi-stock screening against pre-computed DB ("RSI < 30 AND ROE > 20%")
- [ ] Portfolio review (requires Demat data integration via FinWin)
- [ ] RAG pipeline for annual reports / conference call transcripts
- [ ] Nudge system (lower circuit warnings, pledge alerts before buy)
- [ ] FinWin app integration (embed chat inside the trading UI)
- **Demo-able:** "Review my portfolio" / "Find undervalued IT stocks"

**Timeline note:** 12 weeks is achievable with 2-3 developers. Solo developer should plan 20-24 weeks. For MVP, start with just the top 10-20 popular stocks if resources are tight, expand to Nifty 500 after validation.

---

## 8. Cost Estimates

### 8.1 Demo Cost (Tomorrow)

| Item | Cost |
|------|------|
| Live price data | ₹0 (`yfinance` — 15 min delayed, fine for demo) |
| Fundamental data | ₹0 (scrape Screener.in or use cached data) |
| News sentiment | ₹0 (Google News RSS + FinBERT) |
| LLM API | ₹0–500 (Claude/OpenAI free tier covers demo usage) |
| Hosting | ₹0 (run locally on laptop) |
| **Total Demo** | **₹0** |

### 8.2 MVP Monthly Cost (Production)

| Item | Monthly Cost |
|------|-------------|
| Broker API — Angel One SmartAPI (free) or Kite Connect (paid) | ₹0–2,000 |
| LLM API (Claude Sonnet / GPT-4o) — ~1000 queries/day estimate | ₹5,000–15,000 |
| Server (AWS/GCP — 2 instances: API + scraping worker) | ₹8,000–12,000 |
| Apify (optional, for managed Screener.in scraping) | ₹0–3,000 |
| Redis + PostgreSQL (managed) | ₹3,000 |
| **Total MVP** | **₹16,000–35,000/mo** |

### 8.3 How to Reduce LLM Cost Over Time
- Fine-tune a smaller model (Llama 4) for common queries — eliminates per-call API cost
- Cache frequent queries ("What's the P/E of Reliance?" → same answer all day)
- Use Claude Haiku / GPT-4o-mini for simple price lookups, full model only for complex analysis

---

## 9. Demo Plan (For Raman Sir)

### What to Show:
1. **Live conversation** — Ask Mr. Market about 2-3 popular stocks (Reliance, Zomato, TCS)
2. **Technical setup** — "Give me a trade setup for Reliance" → shows entry/exit/SL with reasoning
3. **News correlation** — "Why is [stock] falling today?" → shows sentiment-tagged news
4. **Shareholding check** — "Who owns Zomato?" → FII/DII breakdown, promoter info
5. **Risk guardrail** — Show how bot responds differently to aggressive vs conservative users
6. **Competitor comparison** — The differentiator table from Section 2.3 (no one else does all this in a chat)
7. **Data architecture** — Briefly explain the two-layer model (pre-computed screening + live queries)

### What to Emphasize:
- Mr. Market replaces 4-5 apps (Screener, TradingView, Moneycontrol, Trendlyne, StockEdge) in one chat
- Zero marginal cost for data (scraping + free APIs) — only LLM API cost scales with usage
- SEBI compliance is built-in from day 1, not an afterthought
- FinWin integration means users never leave the trading app

### What NOT to Promise:
- Autonomous buy/sell execution (regulatory minefield — SEBI would require IA registration)
- 100% accuracy on technical levels (always probabilistic)
- Real-time millisecond data (we're a trading assistant, not an HFT system)
- Guaranteed returns or performance claims

---

## 10. Open Questions for Team Discussion

1. **FinWin status:** Is FinWin already built/live? If yes, demo should show integration. If in development, demo Mr. Market standalone and pitch integration story verbally.

2. **Broker integration:** Start with Angel One SmartAPI (free) for MVP? Or go directly with Kite Connect (₹2k/mo) for reliability?

3. **SEBI registration:** Disclaimer model for MVP, or start RA/IA registration process now? Jarvis Invest's SEBI registration gives them credibility — should FinWin pursue this?

4. **Monetization model:** Freemium (basic free, advanced paid)? Bundled with FinWin subscription? Or usage-based pricing?

5. **LLM choice for production:** Claude Sonnet (better reasoning, tool-use) vs GPT-4o (cheaper at scale) vs fine-tuned Llama 4 (self-hosted, zero per-call cost but high upfront effort)?

6. **Stock coverage:** Start with Nifty 500 or narrow to top 50 for faster launch?

7. **Demo readiness:** For tomorrow — is there any working prototype already, or are we doing a concept walkthrough/deck?