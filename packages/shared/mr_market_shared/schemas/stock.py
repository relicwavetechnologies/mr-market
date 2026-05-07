"""Pydantic v2 schemas for stock-related data."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class StockBase(BaseModel):
    """Minimal stock representation."""

    model_config = ConfigDict(from_attributes=True)

    ticker: str
    company_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    cap: str | None = None


class StockDetail(StockBase):
    """Full stock details including listing and index membership."""

    nse_listed: bool = True
    bse_code: str | None = None
    market_cap_cr: Decimal | None = None
    is_nifty50: bool = False
    is_nifty500: bool = False
    is_fno: bool = False
    created_at: datetime | None = None


class PriceData(BaseModel):
    """OHLCV price bar for a single timestamp."""

    model_config = ConfigDict(from_attributes=True)

    ticker: str
    timestamp: datetime
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    volume: int | None = None
    source: str | None = None


class FundamentalsData(BaseModel):
    """Fundamental analysis snapshot."""

    model_config = ConfigDict(from_attributes=True)

    ticker: str
    scraped_date: date
    market_cap: Decimal | None = None
    pe: Decimal | None = None
    pe_industry: Decimal | None = None
    pb: Decimal | None = None
    roe: Decimal | None = None
    roce: Decimal | None = None
    debt_equity: Decimal | None = None
    revenue_growth_pct: Decimal | None = None
    profit_growth_pct: Decimal | None = None
    dividend_yield_pct: Decimal | None = None
    eps: Decimal | None = None
    book_value: Decimal | None = None
    confidence: str | None = None


class TechnicalsData(BaseModel):
    """Technical indicators for a single date."""

    model_config = ConfigDict(from_attributes=True)

    ticker: str
    computed_date: date
    rsi_14: Decimal | None = None
    macd: Decimal | None = None
    macd_signal: Decimal | None = None
    bb_upper: Decimal | None = None
    bb_lower: Decimal | None = None
    sma_20: Decimal | None = None
    sma_50: Decimal | None = None
    sma_200: Decimal | None = None
    ema_20: Decimal | None = None
    pivot: Decimal | None = None
    support_1: Decimal | None = None
    support_2: Decimal | None = None
    resistance_1: Decimal | None = None
    resistance_2: Decimal | None = None
    atr: Decimal | None = None
    trend: str | None = None


class HoldingData(BaseModel):
    """Quarterly shareholding pattern."""

    model_config = ConfigDict(from_attributes=True)

    ticker: str
    quarter: str
    promoter_pct: Decimal | None = None
    promoter_pledge_pct: Decimal | None = None
    fii_pct: Decimal | None = None
    dii_pct: Decimal | None = None
    retail_pct: Decimal | None = None
    fii_change: Decimal | None = None
