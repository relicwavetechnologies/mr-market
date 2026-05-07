# Mr. Market — SEBI Compliance Notes

## Overview

Mr. Market is an AI-powered research and educational tool. It is **not** a SEBI-registered investment adviser (RIA) or research analyst (RA). All outputs are structured to comply with SEBI guidelines for information dissemination.

---

## Disclaimer Requirements

### Mandatory Disclaimer

Every response that discusses specific stocks, trade ideas, or portfolio suggestions must include the following disclaimer:

> **Disclaimer:** Mr. Market is an AI-powered research tool, not a SEBI-registered investment adviser. All information is for educational purposes only and does not constitute buy/sell/hold recommendations. Past performance does not guarantee future results. Always consult a qualified financial adviser before making investment decisions. Investments in securities are subject to market risks; read all related documents carefully.

### Implementation

- The `Disclaimer` component is rendered at the bottom of the chat interface at all times.
- The API includes a `disclaimer` field in chat responses when the content is trade-related.
- The compliance agent automatically injects disclaimers when detecting recommendation-like language.

---

## Risk Profile Gate

### Purpose

Before providing any analysis, the user must complete a risk profile assessment. This ensures that the system can tailor its language and warnings appropriately.

### Risk Levels

| Level         | Description                                                       |
|---------------|-------------------------------------------------------------------|
| Conservative  | Capital preservation focus; large-cap, dividend-paying stocks     |
| Moderate      | Balanced growth and value; mixed market-cap exposure              |
| Aggressive    | High-growth focus; momentum, mid/small caps, higher volatility    |

### Enforcement

- The frontend redirects unonboarded users to the risk profile questionnaire.
- The backend validates that a risk profile exists before processing analysis requests.
- Responses are framed according to the user's risk level (e.g., volatility warnings for conservative profiles).

---

## Nudge Triggers

The system proactively surfaces risk warnings and educational nudges in these scenarios:

### 1. High Volatility Alert
When a stock's ATR or recent price swing exceeds historical norms, the system warns:
> "This stock has shown unusually high volatility recently. Please ensure this aligns with your risk tolerance."

### 2. Concentrated Position Warning
If analysis suggests adding to an already large sector exposure:
> "Note: This would increase your exposure to the [sector] sector. Diversification is generally recommended."

### 3. Penny Stock / SME Warning
For stocks with very low market cap or SME-listed securities:
> "This is a small-cap / SME-listed stock with limited liquidity. Such stocks carry higher risk."

### 4. Results Season Context
During earnings season, the system adds temporal context:
> "Note: [Company] is expected to report Q[X] results on [date]. Stock price may be volatile around this period."

### 5. Leverage / F&O Warning
When discussing F&O strategies or leveraged positions:
> "Derivatives trading involves substantial risk of loss and is not suitable for all investors. Ensure you understand the risks involved."

---

## Data Attribution

All data points in Mr. Market responses include source attribution:

- **Price data**: NSE/BSE official feeds, Yahoo Finance
- **Fundamentals**: Screener.in, MoneyControl, annual reports
- **News**: Economic Times, MoneyControl, Livemint, Reuters
- **Holdings**: BSE/NSE quarterly filings
- **Technicals**: Computed from verified OHLCV data

Confidence levels (HIGH / MEDIUM / LOW) indicate the degree of cross-source agreement and data freshness.
