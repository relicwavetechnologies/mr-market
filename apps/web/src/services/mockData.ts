import type { Conversation, Message, Source } from '@/types';

// ── Mock Conversations ──

const CONV_1_ID = 'conv-reliance-analysis';
const CONV_2_ID = 'conv-tata-motors-falling';
const CONV_3_ID = 'conv-undervalued-it';
const CONV_4_ID = 'conv-hdfc-trade-setup';

export const mockConversations: Conversation[] = [
  {
    id: CONV_1_ID,
    title: 'Should I buy Reliance at current levels?',
    lastMessage: 'Reliance is trading near key technical levels...',
    updatedAt: new Date(),
  },
  {
    id: CONV_2_ID,
    title: 'Why is Tata Motors falling today?',
    lastMessage: 'Tata Motors is down on weak JLR sales...',
    updatedAt: new Date(Date.now() - 2 * 60 * 60 * 1000),
  },
  {
    id: CONV_3_ID,
    title: 'Undervalued IT stocks with high ROE',
    lastMessage: 'Mphasis, LTTS and Coforge screen attractively...',
    updatedAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000),
  },
  {
    id: CONV_4_ID,
    title: 'Trade setup for HDFC Bank',
    lastMessage: 'HDFC Bank is at a key inflection zone...',
    updatedAt: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000),
  },
];

// ── Sources (each list maps to [N] citation indexes) ──

const relianceSources: Source[] = [
  { title: 'NSE India - RELIANCE Live Quote', url: 'https://www.nseindia.com/get-quotes/equity?symbol=RELIANCE', domain: 'nseindia.com' },
  { title: 'Screener.in - Reliance Industries', url: 'https://www.screener.in/company/RELIANCE/', domain: 'screener.in' },
  { title: 'Moneycontrol - Reliance News', url: 'https://www.moneycontrol.com/india/stockpricequote/refineries/relianceindustries/RI', domain: 'moneycontrol.com' },
  { title: 'Trendlyne - RIL Technicals', url: 'https://trendlyne.com/equity/RELIND/', domain: 'trendlyne.com' },
  { title: 'Tickertape - Reliance Scorecard', url: 'https://www.tickertape.in/stocks/reliance-industries-RELI', domain: 'tickertape.in' },
  { title: 'Pulse by Zerodha - RIL', url: 'https://pulse.zerodha.com/', domain: 'pulse.zerodha.com' },
];

const tataSources: Source[] = [
  { title: 'NSE India - TATAMOTORS', url: 'https://www.nseindia.com/get-quotes/equity?symbol=TATAMOTORS', domain: 'nseindia.com' },
  { title: 'Moneycontrol - JLR Q4 Sales', url: 'https://www.moneycontrol.com/news/business/companies/', domain: 'moneycontrol.com' },
  { title: 'Pulse - Tata Motors News', url: 'https://pulse.zerodha.com/', domain: 'pulse.zerodha.com' },
  { title: 'Trendlyne - Shareholding', url: 'https://trendlyne.com/equity/TATAMOTORS/', domain: 'trendlyne.com' },
  { title: 'Tickertape - Auto Sector', url: 'https://www.tickertape.in/sectors/automobile', domain: 'tickertape.in' },
];

const itScreenerSources: Source[] = [
  { title: 'Screener.in - IT Sector Screen', url: 'https://www.screener.in/screens/', domain: 'screener.in' },
  { title: 'Tickertape - Mphasis', url: 'https://www.tickertape.in/stocks/mphasis-MPHA', domain: 'tickertape.in' },
  { title: 'Trendlyne - LTTS', url: 'https://trendlyne.com/equity/LTTS/', domain: 'trendlyne.com' },
  { title: 'Moneycontrol - Coforge', url: 'https://www.moneycontrol.com/india/stockpricequote/computers-software/coforge/CO11', domain: 'moneycontrol.com' },
  { title: 'NSE India - IT Index', url: 'https://www.nseindia.com/market-data/live-equity-market', domain: 'nseindia.com' },
];

const hdfcSources: Source[] = [
  { title: 'NSE India - HDFCBANK', url: 'https://www.nseindia.com/get-quotes/equity?symbol=HDFCBANK', domain: 'nseindia.com' },
  { title: 'Screener.in - HDFC Bank', url: 'https://www.screener.in/company/HDFCBANK/', domain: 'screener.in' },
  { title: 'Trendlyne - HDFC Bank Technicals', url: 'https://trendlyne.com/equity/HDFCBANK/', domain: 'trendlyne.com' },
  { title: 'Tickertape - HDFC Bank Scorecard', url: 'https://www.tickertape.in/stocks/hdfc-bank-HDBK', domain: 'tickertape.in' },
  { title: 'Moneycontrol - HDFC Q4 Preview', url: 'https://www.moneycontrol.com/india/stockpricequote/banks-private-sector/hdfcbank/HDF01', domain: 'moneycontrol.com' },
];

const marketOverviewSources: Source[] = [
  { title: 'NSE India - Market Data', url: 'https://www.nseindia.com/market-data/live-market-indices', domain: 'nseindia.com' },
  { title: 'Moneycontrol - Markets', url: 'https://www.moneycontrol.com/markets/', domain: 'moneycontrol.com' },
  { title: 'Trendlyne - FII/DII Activity', url: 'https://trendlyne.com/fundamentals/fii-dii-activity/', domain: 'trendlyne.com' },
  { title: 'Pulse by Zerodha', url: 'https://pulse.zerodha.com/', domain: 'pulse.zerodha.com' },
  { title: 'Tickertape - Sectors', url: 'https://www.tickertape.in/sectors', domain: 'tickertape.in' },
];

// ── Mock Responses ──

const relianceResponse = `Reliance Industries is trading at **₹1,247.50**, up 0.6% intraday, holding above its 50-day moving average and consolidating below the recent swing high of ₹1,280 [1]. The setup looks constructive for medium-term investors but near-term entries should wait for either a clean breakout above ₹1,280 or a pullback into the ₹1,225–1,235 demand zone [4].

## Latest Movement

- Price action has been range-bound between ₹1,225 and ₹1,280 for the last three weeks, with rising volumes on green days suggesting accumulation [1]
- The 50-DMA at ₹1,220 and 200-DMA at ₹1,185 are both trending up, confirming a primary uptrend [4]
- Delivery percentage has averaged 52% over the last 10 sessions, well above the 6-month average of 41% [1]

## Key Metrics

- **Trailing P/E:** 24.5× vs the energy sector median of 22.1×, modestly premium but justified by the consumer mix [2]
- **ROE:** 15.2%, with ROCE at 12.8% — both improving year-on-year as Jio and Retail compound [2]
- **Debt/Equity:** 0.35, materially lower than 2020 peak of 0.74 after the rights issue and stake sales [5]
- **Revenue growth (YoY):** 12.4%, driven primarily by Retail (+18%) and Digital Services (+11%) [2]

## Technical Outlook

- **RSI (14):** 58.3, neutral with a positive bias — no overbought signal [4]
- **MACD:** Bullish crossover printed three sessions ago, histogram expanding [4]
- **Immediate support:** ₹1,230 (50-DMA confluence with prior breakout level) [4]
- **Immediate resistance:** ₹1,280, a sustained close above this opens up ₹1,340 as the next target [3]

## What to Watch

- Q1 earnings on July 19th — Street expects 9% YoY EBITDA growth, with Retail margin expansion as the key swing factor [3]
- Jio tariff hike rumors — any confirmation lifts ARPU estimates for FY26 by 8–10% [6]
- Crude price trajectory — sustained Brent above $90 pressures O2C margins [3]`;

const tataResponse = `Tata Motors is down **3.2% at ₹742.50** today on a combination of weak Jaguar Land Rover Q4 retail data and broader auto-sector selling pressure [1]. The stock has now broken below its 20-DMA on volume that is 2.3× the 30-day average, indicating institutional distribution rather than retail selling [3].

## Latest Movement

- JLR reported Q4 retail sales down 8% YoY, with China and the UK as the weakest markets [2]
- The Nifty Auto index is down 1.8% today, with M&M and Bajaj Auto also weak — this is sector-wide, not a stock-specific blow-up [5]
- Volume of 4.1 crore shares vs the 30-day average of 1.8 crore confirms institutional selling [1]

## Why It's Falling

- **JLR softness:** Premium SUV demand has cooled in China as luxury consumption normalizes; Range Rover waitlists have shortened [2]
- **EV subsidy review in the UK:** The government announced a review of plug-in incentives, creating uncertainty for JLR's electrification roadmap [3]
- **Margin pressure:** Steel and aluminum input costs are up 6% QoQ, squeezing the commercial vehicle business [5]
- **FII selling:** Foreign holding decreased 1.2 percentage points last quarter, the largest single-quarter drop in 2 years [4]

## Technical Damage

- Stock has decisively broken its 20-DMA at ₹755 with volume confirmation [1]
- Next meaningful support is the 50-DMA at ₹720, then the ₹680 swing low from February [3]
- RSI has dropped to 35.4 — approaching oversold but not yet a contrarian signal [3]
- Daily MACD is below zero with histogram still expanding to the downside [3]

## What to Watch

- JLR's full Q4 earnings release next week — guidance on FY26 wholesales is the key variable [2]
- Steel HRC prices — a roll-over below ₹54,000/tonne would ease the CV margin headwind [5]
- The ₹720 level — a daily close below opens up ₹680, which is also the rising 200-DMA [3]`;

const itScreenerResponse = `Screening the Nifty IT universe for stocks trading below the sector median P/E of 30.2× with ROE above 15% surfaces three clear standouts: **Mphasis, L&T Technology Services, and Coforge** [1]. All three are trading at meaningful discounts to their 52-week highs while maintaining double-digit revenue growth and high return ratios [2].

## Top Picks

- **Mphasis (₹2,145):** P/E 22.1×, ROE 18.4%, trading at a 35% discount to 52-week high; Blackstone-backed with a strengthening BFSI deal pipeline [2]
- **L&T Technology Services (₹4,320):** P/E 25.3×, ROE 21.7%, leader in engineering R&D services with consistent 16%+ revenue growth [3]
- **Coforge (₹5,680):** P/E 27.8×, ROE 24.1%, best-in-class growth among mid-cap IT at 18% YoY but at a slight valuation premium [4]

## Why Mphasis Stands Out

- Trading 35% below its 52-week high after the broader IT correction, the steepest derating among Tier-2 names [2]
- Operating margin steady at 15.8% despite wage inflation — utilization is at 81%, with room to expand [2]
- Order book at ₹4,200 crore, up 14% YoY, with the BFSI vertical (61% of revenue) showing recovery signs [2]
- Consistent dividend payer with a current yield of 1.8%, supportive in a rangebound tape [1]

## Risk Factors

- US BFSI spending remains the swing variable — any 2026 budget cuts at top-5 banking clients would hit revenue [5]
- Currency: a sustained rupee strength below ₹83/USD compresses gross margins by ~50 bps [1]
- Mid-cap IT historically derates faster than large-cap in risk-off tapes [3]

## Screening Methodology

- Universe: Nifty 500 IT sector (BSE/NSE listed) [5]
- Filters applied: P/E < sector median (30.2×), ROE > 15%, revenue growth > 10% YoY, debt/equity < 0.3 [1]
- Ranked by a composite score of valuation discount, growth, and capital efficiency [4]`;

const hdfcResponse = `HDFC Bank is trading at **₹1,642.80**, sitting right at a key technical inflection above both its 20-DMA (₹1,628) and 50-DMA (₹1,615) [1]. The recent MACD crossover and improving credit-growth narrative make it a clean risk-reward setup for a move toward the 52-week high zone at ₹1,750 [3].

## Latest Movement

- Stock has consolidated in a tight ₹1,620–1,665 range for 12 sessions, with declining ATR signaling a coiled spring [3]
- Volume profile shows strong demand at ₹1,615–1,625, the prior resistance that flipped to support [1]
- Bank Nifty relative strength is positive — HDFC Bank has outperformed by 280 bps over the last month [3]

## Trade Setup

- **Entry zone:** ₹1,635–1,645 (current consolidation range) [3]
- **Stop loss:** ₹1,600 — below the 50-DMA, roughly -2.6% from spot [3]
- **Target 1:** ₹1,700 (recent swing high), implies +3.5% [3]
- **Target 2:** ₹1,750 (52-week high zone), implies +6.5% [3]
- **Risk-reward:** ~1:2.5, favorable for a positional swing trade [3]

## Fundamental Backdrop

- **P/E:** 19.8× vs the private-bank peer median of 22.3×, attractive after the post-merger derating [2]
- **ROE:** 17.1%, best-in-class among private banks even after the HDFC Ltd absorption [2]
- **Asset quality:** Gross NPA at 1.24%, slippages contained at sub-1% — among the cleanest books in the sector [2]
- **Advances growth:** 19.4% YoY, with retail loan growth accelerating into double digits [4]

## Catalysts

- Q4 results on July 20th — consensus expects 18–20% PAT growth and a NIM uptick of 5–10 bps [5]
- RBI rate cycle — every 25 bps cut helps NIMs by ~6 bps for HDFC Bank's deposit-heavy book [4]
- Index weight readjustment after the merger anniversary may bring incremental passive flows [3]

## Risks

- Any unsecured retail asset-quality surprise would reset the multiple [2]
- Competition from fintechs in the unsecured personal-loan space remains a structural overhang [4]
- Global rate volatility could compress treasury gains [5]`;

const marketOverviewResponse = `The Indian market is showing **mixed but constructive signals** today, with Nifty 50 at 22,450 (+0.3%) and Bank Nifty leading on the upside while auto and pharma drag [1]. Breadth is positive with an advance-decline ratio of 1.3:1, but India VIX at 13.2 suggests complacency rather than conviction [2].

## Today's Tape

- **Nifty 50:** 22,450 (+0.3%), holding above the 20-DMA at 22,380 with 22,600 as immediate resistance [1]
- **Bank Nifty:** +0.5%, led by HDFC Bank and ICICI Bank on improving credit-growth narrative [1]
- **Nifty Auto:** -0.8%, weighed down by Tata Motors and M&M on weak JLR data and EV-subsidy uncertainty [5]

## Flows

- **FII:** Net buyers of ₹1,200 crore in cash today, the third consecutive day of inflows [3]
- **DII:** Net sellers of ₹450 crore, profit-booking after a strong April; mutual funds remain net buyers MTD [3]
- **F&O:** PCR (Open Interest) at 1.18, mildly bullish; max pain for the current expiry sits at 22,400 [4]

## Sector Heatmap

- **Outperformers:** Bank Nifty (+0.5%), Nifty Realty (+1.2%), Nifty PSU Bank (+0.9%) [5]
- **Underperformers:** Nifty Auto (-0.8%), Nifty Pharma (-0.4%), Nifty Metal (-0.3%) [5]

## What to Watch

- Resistance at 22,600 (previous swing high) — a sustained breakout opens the path to 23,000 [1]
- Crude trajectory — a sustained move above $90 Brent would pressure margins for OMCs and paints [4]
- US 10-year yield — any move above 4.6% historically triggers FII outflows [3]`;

const generalKnowledgeResponse = `Technical indicators like **RSI** and **MACD** are the two most widely used momentum tools in Indian retail charting, and understanding their mechanics helps you avoid the most common false signals [1].

## RSI (Relative Strength Index)

- A bounded oscillator that ranges from 0 to 100, calculated from the average of recent gains versus losses over a lookback period (default 14 sessions) [2]
- Values above **70** are conventionally "overbought," below **30** are "oversold" — but in strong trends RSI can stay overbought for weeks [3]
- The most reliable signal is **divergence:** price making a new high while RSI prints a lower high often precedes a reversal [3]

## MACD (Moving Average Convergence Divergence)

- The difference between the 12-period and 26-period exponential moving averages, with a 9-period signal line on top [2]
- A **bullish crossover** (MACD line crossing above signal line) is the most basic entry trigger [4]
- The histogram (MACD minus signal) tells you the momentum of momentum — when it starts contracting on a strong move, the trend is weakening [4]

## How They Work Together

- Use MACD for trend direction and RSI for entry timing within the trend [1]
- Avoid trading RSI overbought/oversold signals against a strong MACD trend — these are the highest-failure setups [3]
- Both are lagging indicators — they confirm what's already happening, they don't predict [2]

## Common Mistakes

- Treating RSI 70/30 as automatic sell/buy signals without checking the underlying trend [5]
- Reacting to MACD crossovers on intraday timeframes, which produce far more false signals than daily charts [4]
- Ignoring volume — both indicators are far more reliable when confirmed by above-average volume [1]`;

// ── Mock Messages (existing conversations) ──

export const mockMessages: Record<string, Message[]> = {
  [CONV_1_ID]: [
    {
      id: 'msg-r1',
      role: 'user',
      content: 'Should I buy Reliance at current levels?',
      timestamp: new Date(Date.now() - 10 * 60 * 1000),
    },
    {
      id: 'msg-r2',
      role: 'assistant',
      content: relianceResponse,
      sources: relianceSources,
      timestamp: new Date(Date.now() - 9 * 60 * 1000),
      completionTime: 2.3,
    },
  ],
  [CONV_2_ID]: [
    {
      id: 'msg-t1',
      role: 'user',
      content: 'Why is Tata Motors falling today?',
      timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000),
    },
    {
      id: 'msg-t2',
      role: 'assistant',
      content: tataResponse,
      sources: tataSources,
      timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000 + 30 * 1000),
      completionTime: 3.1,
    },
  ],
  [CONV_3_ID]: [
    {
      id: 'msg-i1',
      role: 'user',
      content: 'Show me undervalued IT stocks with high ROE',
      timestamp: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000),
    },
    {
      id: 'msg-i2',
      role: 'assistant',
      content: itScreenerResponse,
      sources: itScreenerSources,
      timestamp: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000 + 45 * 1000),
      completionTime: 4.2,
    },
  ],
  [CONV_4_ID]: [
    {
      id: 'msg-h1',
      role: 'user',
      content: 'Give me a trade setup for HDFC Bank',
      timestamp: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000),
    },
    {
      id: 'msg-h2',
      role: 'assistant',
      content: hdfcResponse,
      sources: hdfcSources,
      timestamp: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000 + 35 * 1000),
      completionTime: 2.8,
    },
  ],
};

// ── Response lookup for new queries ──

interface MockResponseEntry {
  content: string;
  sources: Source[];
}

const MOCK_RESPONSE_MAP: { keywords: string[]; response: MockResponseEntry }[] = [
  {
    keywords: ['reliance', 'ril'],
    response: { content: relianceResponse, sources: relianceSources },
  },
  {
    keywords: ['tata motors', 'falling', 'tatamotors', 'why is'],
    response: { content: tataResponse, sources: tataSources },
  },
  {
    keywords: ['undervalued', 'screen', 'roe', 'it stocks', 'mphasis', 'coforge'],
    response: { content: itScreenerResponse, sources: itScreenerSources },
  },
  {
    keywords: ['hdfc', 'trade setup', 'hdfcbank'],
    response: { content: hdfcResponse, sources: hdfcSources },
  },
  {
    keywords: ['rsi', 'macd', 'indicator', 'learn', 'explain'],
    response: { content: generalKnowledgeResponse, sources: relianceSources },
  },
  {
    keywords: ['market', 'nifty', 'overview', 'sensex'],
    response: { content: marketOverviewResponse, sources: marketOverviewSources },
  },
];

const defaultResponse: MockResponseEntry = {
  content: marketOverviewResponse,
  sources: marketOverviewSources,
};

export function getMockResponse(query: string): MockResponseEntry {
  const q = query.toLowerCase();
  for (const entry of MOCK_RESPONSE_MAP) {
    if (entry.keywords.some((kw) => q.includes(kw))) {
      return entry.response;
    }
  }
  return defaultResponse;
}
