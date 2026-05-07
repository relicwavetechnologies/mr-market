# Mr. Market — API Documentation

Base URL: `/api/v1`

---

## Health

### `GET /api/v1/health`

Returns the health status of the API and its dependencies.

**Response:**
```json
{
  "status": "ok",
  "database": "connected",
  "redis": "connected",
  "qdrant": "connected"
}
```

---

## Chat

### `POST /api/v1/chat`

Send a chat message and receive a complete (non-streaming) response.

**Headers:** `Authorization: Bearer <token>`

**Request body:**
```json
{
  "message": "Analyse RELIANCE",
  "conversation_id": "uuid (optional)"
}
```

**Response:**
```json
{
  "reply": "Here is the analysis for Reliance Industries...",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "sources": [
    { "name": "Screener.in", "url": "https://screener.in/..." }
  ],
  "disclaimer": "This is not investment advice..."
}
```

### `WebSocket /api/v1/chat/ws?token=<jwt>`

Stream chat responses over a WebSocket connection.

**Client sends:**
```json
{ "message": "Is TCS overvalued?", "conversation_id": "uuid (optional)" }
```

**Server sends (streaming chunks):**
```json
{ "type": "chunk", "content": "Based on current..." }
```

**Server sends (completion):**
```json
{
  "type": "done",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "sources": [...],
  "disclaimer": "..."
}
```

---

## Analyze

### `GET /api/v1/analyze/{ticker}`

Fetch a comprehensive analysis for a given NSE ticker.

**Headers:** `Authorization: Bearer <token>`

**Path parameters:**
- `ticker` — NSE ticker symbol (e.g., `RELIANCE`, `TCS`, `INFY`)

**Response:**
```json
{
  "ticker": "RELIANCE",
  "price": { "current": 2450.50, "change": 25.30, "change_pct": 1.04 },
  "fundamentals": {
    "pe": 28.5, "pb": 2.1, "roe": 12.3, "roce": 14.5,
    "debt_equity": 0.45, "market_cap": 1660000,
    "dividend_yield": 0.35
  },
  "technicals": {
    "rsi_14": 55.2, "macd": 12.5, "macd_signal": 10.8,
    "sma_20": 2420.0, "sma_50": 2380.0, "sma_200": 2300.0,
    "trend": "bullish", "support_1": 2400.0, "resistance_1": 2500.0
  },
  "news": [
    { "headline": "Reliance Q3 results...", "source": "ET", "url": "...", "published_at": "..." }
  ],
  "holding": {
    "promoter": 50.3, "fii": 23.1, "dii": 14.5, "retail": 12.1, "fii_change": 0.5
  },
  "confidence": "HIGH"
}
```

---

## Portfolio

### `POST /api/v1/portfolio/risk-profile`

Set or update the user's risk profile.

**Headers:** `Authorization: Bearer <token>`

**Request body:**
```json
{
  "level": "moderate",
  "preferences": {}
}
```

**Response:** `200 OK`

### `GET /api/v1/portfolio/risk-profile`

Retrieve the current user's risk profile.

**Response:**
```json
{
  "level": "moderate",
  "preferences": {}
}
```

---

## Root

### `GET /`

Root health probe.

**Response:**
```json
{
  "status": "ok",
  "service": "mr-market-api"
}
```

---

## Error Responses

All errors follow a consistent format:

```json
{
  "detail": "Error description"
}
```

| Status | Meaning                |
|--------|------------------------|
| 400    | Bad request            |
| 401    | Unauthorized           |
| 404    | Resource not found     |
| 422    | Validation error       |
| 429    | Rate limit exceeded    |
| 500    | Internal server error  |
