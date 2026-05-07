import type { Source } from "@/types";

interface MockResponse {
  content: string;
  sources: Source[];
}

const MOCK_RESPONSES: MockResponse[] = [
  {
    content: `## Reliance Industries Ltd (RELIANCE) - Analysis

**Current Price:** Rs 2,847.30 (+1.2%) [1]

### Technical Overview
- **RSI (14):** 58.3 -- Neutral zone, neither overbought nor oversold
- **MACD:** Bullish crossover observed on the daily chart [2]
- **Support:** Rs 2,780 (SMA 50) | **Resistance:** Rs 2,920 (previous swing high)
- **Trend:** Short-term bullish, trading above 20-DMA and 50-DMA

### Fundamental Snapshot
| Metric | Value | Industry Avg |
|--------|-------|-------------|
| P/E Ratio | 28.4x | 24.1x |
| ROE | 8.9% | 12.3% |
| D/E Ratio | 0.38 | 0.52 |
| Dividend Yield | 0.32% | 0.85% |

### Key Observations
1. **Jio Platforms** continues to drive revenue growth with 450M+ subscribers [3]
2. Retail segment (Reliance Retail) reported 18% YoY revenue growth
3. O2C business margins have stabilized after recent volatility
4. FII holding increased by 0.4% in the last quarter [4]

### Trade Setup
- **Entry:** Rs 2,830-2,850 (current levels)
- **Target 1:** Rs 2,920 | **Target 2:** Rs 3,000
- **Stop Loss:** Rs 2,750 (below 50-DMA)
- **Risk-Reward:** 1:2.1

> **Note:** This is a strong momentum play, but global crude prices remain a risk factor for the O2C segment. Monitor quarterly results closely.`,
    sources: [
      { title: "NSE India - Live Price", url: "https://www.nseindia.com", snippet: "Real-time price data from NSE" },
      { title: "TradingView - Technical Chart", url: "https://tradingview.com", snippet: "MACD crossover signal on daily timeframe" },
      { title: "Moneycontrol - Jio Subscribers", url: "https://moneycontrol.com", snippet: "Jio Platforms crosses 450M subscriber mark" },
      { title: "BSE Filings - Shareholding", url: "https://bseindia.com", snippet: "Q3 FY26 shareholding pattern" },
    ],
  },
  {
    content: `## TCS Trade Setup

**Tata Consultancy Services** is currently showing a promising setup for swing traders.

### Current Status
- **Price:** Rs 3,842.15 (-0.3%) [1]
- **Market Cap:** Rs 13.9L Cr
- **52-Week Range:** Rs 3,310 - Rs 4,250

### Technical Analysis
The stock has pulled back to its **200-DMA (Rs 3,820)** which historically acts as strong support [2]. Key observations:

1. **Volume Profile:** Below-average volume on the pullback suggests exhaustion of selling pressure
2. **Fibonacci Retracement:** Price sitting at 61.8% retracement of the Apr-May rally
3. **RSI:** 42.3 -- approaching oversold territory

### Recommended Setup
| Parameter | Value |
|-----------|-------|
| Entry Zone | Rs 3,820 - 3,850 |
| Stop Loss | Rs 3,740 |
| Target 1 | Rs 3,980 |
| Target 2 | Rs 4,100 |
| Timeframe | 2-4 weeks |

### Risk Factors
- US recession fears could impact IT spending outlook [3]
- INR appreciation may pressure margins
- Management guidance was cautious for FY27

> **SEBI Disclaimer:** This is not investment advice. Past performance does not guarantee future results. Please consult your financial advisor before making investment decisions.`,
    sources: [
      { title: "NSE India - TCS Price", url: "https://www.nseindia.com", snippet: "Live market data" },
      { title: "Screener.in - TCS Fundamentals", url: "https://screener.in", snippet: "Historical moving average data" },
      { title: "Economic Times - IT Sector", url: "https://economictimes.com", snippet: "US recession fears and IT outlook" },
    ],
  },
  {
    content: `## Why is Tata Motors Falling Today?

Tata Motors is down **-3.2%** at Rs 742.50 today. Here's what's driving the decline [1]:

### Primary Reasons

**1. JLR Sales Miss**
Jaguar Land Rover reported Q4 sales below estimates, with retail sales declining 8% YoY in key markets including China and the UK [2].

**2. EV Subsidy Uncertainty**
The UK government announced a review of EV purchase incentives, creating uncertainty for JLR's electric vehicle roadmap [3].

**3. Broader Auto Sector Weakness**
The Nifty Auto index is down 1.8% today, with across-the-board selling. Rising input costs (steel, aluminum) are pressuring margins sector-wide.

### Technical Damage
- Stock has broken below its **20-DMA** (Rs 755)
- Next support at **Rs 720** (50-DMA)
- RSI has dropped to **35.4** -- approaching oversold
- Volume is **2.3x average**, indicating institutional selling

### Shareholding Context
- FII holding **decreased** by 1.2% last quarter [4]
- Promoter holding remains steady at 46.4%
- Mutual fund buying has slowed

### What to Watch
- JLR's full earnings report (expected next week)
- Steel price trajectory for margin outlook
- Rs 720 support level -- a break below could target Rs 680

> Markets can overreact to short-term news. If you hold the stock for fundamental reasons, the current dip may be a buying opportunity, but wait for Rs 720 support to hold.`,
    sources: [
      { title: "NSE India - Live Data", url: "https://www.nseindia.com", snippet: "Intraday price movement" },
      { title: "Reuters - JLR Sales", url: "https://reuters.com", snippet: "JLR Q4 retail sales decline 8% YoY" },
      { title: "BBC News - UK EV Policy", url: "https://bbc.com", snippet: "UK government reviews EV purchase incentives" },
      { title: "BSE Filings", url: "https://bseindia.com", snippet: "Latest shareholding data" },
    ],
  },
  {
    content: `## Undervalued IT Stocks with RSI < 30

Based on screening the Nifty IT universe, here are stocks meeting your criteria [1]:

### Results

| Stock | Price | RSI (14) | P/E | ROE | Score |
|-------|-------|----------|-----|-----|-------|
| **Mphasis** | Rs 2,145 | 27.8 | 22.1x | 18.4% | 8.2/10 |
| **L&T Technology** | Rs 4,320 | 29.1 | 25.3x | 21.7% | 7.8/10 |
| **Coforge** | Rs 5,680 | 28.4 | 27.8x | 24.1% | 7.5/10 |

### Deep Dive: Mphasis (Top Pick)

**Why it stands out:**
- Trading at a **35% discount** to 52-week high [2]
- Blackstone-backed with strong deal pipeline
- BFSI vertical showing recovery signs
- Consistent dividend payer (yield: 1.8%)

**Technical Setup:**
- RSI at 27.8 suggests the stock is **oversold**
- Price at lower Bollinger Band -- potential mean reversion play
- Key support: Rs 2,080 (previous accumulation zone)

**Fundamentals:**
- Revenue growth: 12% YoY
- Operating margin: 15.8% (stable)
- Order book: Rs 4,200 Cr (healthy)

### Screener Methodology
Filtered Nifty 500 stocks in the IT sector with:
- RSI (14-day) < 30
- P/E ratio below sector median (30.2x)
- ROE > 15%
- Positive revenue growth [3]

> **Note:** Oversold stocks can remain oversold. Use technical confirmation (RSI divergence, volume surge) before entering positions.`,
    sources: [
      { title: "Pre-computed screening DB", url: undefined, snippet: "Nightly batch computation for Nifty 500" },
      { title: "Screener.in - Mphasis", url: "https://screener.in", snippet: "Fundamental data and valuations" },
      { title: "Mr. Market Screening Engine", url: undefined, snippet: "Custom multi-factor screening algorithm" },
    ],
  },
];

/**
 * Simulates a streaming response by yielding characters at randomized intervals.
 */
export async function streamMockResponse(
  query: string,
  onChunk: (chunk: string) => void,
  onSources: (sources: Source[]) => void,
  onDone: () => void,
): Promise<void> {
  // Pick a response based on simple keyword matching
  const q = query.toLowerCase();
  let responseIndex = 0;
  if (q.includes("tcs") || q.includes("trade setup")) {
    responseIndex = 1;
  } else if (q.includes("falling") || q.includes("moving") || q.includes("tata motors")) {
    responseIndex = 2;
  } else if (q.includes("screen") || q.includes("undervalued") || q.includes("rsi")) {
    responseIndex = 3;
  }

  const response = MOCK_RESPONSES[responseIndex];
  const { content, sources } = response;

  // Send sources early
  onSources(sources);

  // Stream character by character with randomized delays
  for (let i = 0; i < content.length; i++) {
    onChunk(content[i]);

    // Vary speed: faster for spaces/common chars, slower at punctuation
    const char = content[i];
    let delay: number;
    if (char === "\n") {
      delay = 15 + Math.random() * 25;
    } else if (char === "." || char === "!" || char === "?") {
      delay = 30 + Math.random() * 40;
    } else if (char === "|" || char === "-") {
      delay = 2 + Math.random() * 5;
    } else {
      delay = 5 + Math.random() * 12;
    }
    await new Promise((resolve) => setTimeout(resolve, delay));
  }

  onDone();
}
