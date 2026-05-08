"""Unit tests for the portfolio CSV + CDSL paste parsers (P3-A4).

DB-side persistence + auth + universe-gate behaviour live in
`tests/test_portfolio_api.py`. This file is pure-Python: tests cover the
parsers and `collapse_duplicates`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.data.portfolio_import import (
    ParsedHolding,
    collapse_duplicates,
    detect_format,
    parse_cdsl_paste,
    parse_csv,
    parse_text,
)


# ---------------------------------------------------------------------------
# detect_format
# ---------------------------------------------------------------------------


class TestDetectFormat:
    def test_csv_detected(self):
        assert detect_format("ticker,quantity,avg_price\nRELIANCE,100,1380.50") == "csv"

    def test_paste_detected(self):
        assert detect_format("RELIANCE\t100\t1380.50") == "cdsl_paste"

    def test_paste_detected_when_whitespace(self):
        assert detect_format("RELIANCE  100  1380.50") == "cdsl_paste"


# ---------------------------------------------------------------------------
# parse_csv
# ---------------------------------------------------------------------------


class TestParseCsv:
    def test_canonical_csv(self):
        text = (
            "ticker,quantity,avg_price\n"
            "RELIANCE,100,1280.50\n"
            "TCS,25,2150.00\n"
        )
        report = parse_csv(text)
        assert len(report.holdings) == 2
        assert report.holdings[0] == ParsedHolding(
            ticker="RELIANCE", quantity=100, avg_price=Decimal("1280.50")
        )
        assert report.skipped_rows == []
        assert report.detected_format == "csv"

    def test_alternative_column_names(self):
        # Many sources use "Symbol" instead of "ticker", "Qty" instead of "Quantity".
        text = "Symbol,Qty,Avg Cost\nRELIANCE,100,1280.50\n"
        report = parse_csv(text)
        assert len(report.holdings) == 1
        assert report.holdings[0].ticker == "RELIANCE"

    def test_avg_price_optional(self):
        text = "ticker,quantity\nRELIANCE,100\n"
        report = parse_csv(text)
        assert len(report.holdings) == 1
        assert report.holdings[0].avg_price is None

    def test_skips_blank_lines(self):
        text = "ticker,quantity\n\nRELIANCE,100\n\n\n"
        report = parse_csv(text)
        assert len(report.holdings) == 1

    def test_drops_zero_or_negative_quantity(self):
        text = "ticker,quantity\nRELIANCE,0\nTCS,-5\nINFY,10\n"
        report = parse_csv(text)
        assert len(report.holdings) == 1
        assert report.holdings[0].ticker == "INFY"
        assert len(report.skipped_rows) == 2

    def test_drops_blank_ticker(self):
        text = "ticker,quantity\n,100\nRELIANCE,50\n"
        report = parse_csv(text)
        assert len(report.holdings) == 1
        assert report.holdings[0].ticker == "RELIANCE"

    def test_handles_commas_in_quantity(self):
        text = "ticker,quantity,avg_price\nRELIANCE,\"1,000\",1280.50\n"
        report = parse_csv(text)
        assert report.holdings[0].quantity == 1000

    def test_uppercases_ticker(self):
        text = "ticker,quantity\nreliance,100\n"
        report = parse_csv(text)
        assert report.holdings[0].ticker == "RELIANCE"

    def test_unknown_header_returns_empty(self):
        text = "foo,bar\nRELIANCE,100\n"
        report = parse_csv(text)
        assert report.holdings == []
        assert report.skipped_rows  # has a 'could not find columns' note

    def test_empty_input(self):
        report = parse_csv("")
        assert report.holdings == []
        assert report.skipped_rows == ["empty input"]


# ---------------------------------------------------------------------------
# parse_cdsl_paste
# ---------------------------------------------------------------------------


class TestParseCdslPaste:
    def test_zerodha_holdings_paste_tab(self):
        text = (
            "Instrument\tQty\tAvg cost\tLTP\tCur val\tP&L\tNet chg\n"
            "RELIANCE\t100\t1280.50\t1436.10\t143610.00\t+15560.00\t+12.15%\n"
            "TCS\t25\t2150.00\t2401.40\t60035.00\t+6285.00\t+11.68%\n"
        )
        report = parse_cdsl_paste(text)
        assert len(report.holdings) == 2
        assert report.holdings[0] == ParsedHolding(
            ticker="RELIANCE", quantity=100, avg_price=Decimal("1280.50")
        )

    def test_whitespace_separated_paste(self):
        text = (
            "Instrument  Qty  Avg cost  LTP\n"
            "RELIANCE  100  1280.50  1436.10\n"
            "TCS       25   2150.00  2401.40\n"
        )
        report = parse_cdsl_paste(text)
        assert len(report.holdings) == 2

    def test_skips_header_row(self):
        text = (
            "Instrument\tQty\tAvg\n"
            "RELIANCE\t100\t1280.50\n"
        )
        report = parse_cdsl_paste(text)
        assert len(report.holdings) == 1
        # Header row was correctly identified as such (no skip warning).
        assert "Instrument" not in str(report.skipped_rows)

    def test_handles_rupee_and_commas(self):
        text = "RELIANCE  1,000  ₹1,280.50  ₹1,436.10\n"
        report = parse_cdsl_paste(text)
        assert report.holdings[0].quantity == 1000
        assert report.holdings[0].avg_price == Decimal("1280.50")

    def test_handles_dashes_in_ticker(self):
        text = "BAJAJ-AUTO\t10\t8500.00\n"
        report = parse_cdsl_paste(text)
        assert report.holdings[0].ticker == "BAJAJ-AUTO"

    def test_handles_ampersand_in_ticker(self):
        text = "M&M\t5\t1500.00\n"
        report = parse_cdsl_paste(text)
        assert report.holdings[0].ticker == "M&M"

    def test_skips_isin_lines(self):
        # ISINs are 12-char alphanumeric starting with 2 letters (country code).
        text = "INE002A01018\t100\t1280.50\n"
        report = parse_cdsl_paste(text)
        # ISIN line should be skipped (no NSE symbol).
        assert report.holdings == []

    def test_skips_blank_lines(self):
        text = "\n\nRELIANCE\t100\t1280.50\n\n"
        report = parse_cdsl_paste(text)
        assert len(report.holdings) == 1

    def test_avg_price_optional(self):
        # First numeric → quantity. No second numeric → avg_price = None.
        text = "RELIANCE\t100\n"
        report = parse_cdsl_paste(text)
        assert report.holdings[0].avg_price is None


# ---------------------------------------------------------------------------
# parse_text auto-detection
# ---------------------------------------------------------------------------


class TestParseText:
    def test_auto_detects_csv(self):
        report = parse_text("ticker,quantity\nRELIANCE,100\n")
        assert report.detected_format == "csv"
        assert report.holdings[0].ticker == "RELIANCE"

    def test_auto_detects_paste(self):
        report = parse_text("RELIANCE\t100\t1280.50\n")
        assert report.detected_format == "cdsl_paste"

    def test_explicit_format_overrides(self):
        # Force CSV parser on a paste blob — should fail to find columns.
        report = parse_text("RELIANCE\t100\n", format="csv")
        assert report.detected_format == "csv"
        assert report.holdings == []  # no column header → nothing parsed

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError, match="unknown format"):
            parse_text("RELIANCE 100", format="excel")


# ---------------------------------------------------------------------------
# collapse_duplicates
# ---------------------------------------------------------------------------


class TestCollapseDuplicates:
    def test_single_row_unchanged(self):
        items = [ParsedHolding("RELIANCE", 100, Decimal("1280.50"))]
        out = collapse_duplicates(items)
        assert out == items

    def test_sums_quantities(self):
        items = [
            ParsedHolding("RELIANCE", 100, Decimal("1200")),
            ParsedHolding("RELIANCE", 50, Decimal("1400")),
        ]
        out = collapse_duplicates(items)
        assert len(out) == 1
        assert out[0].quantity == 150
        # Weighted avg: (100*1200 + 50*1400) / 150 = 1266.666...
        assert abs(float(out[0].avg_price) - 1266.6667) < 0.001

    def test_handles_missing_prices(self):
        items = [
            ParsedHolding("RELIANCE", 100, None),
            ParsedHolding("RELIANCE", 50, Decimal("1400")),
        ]
        out = collapse_duplicates(items)
        # Only the priced row contributes to weighted avg.
        assert out[0].quantity == 150
        assert out[0].avg_price == Decimal("1400")

    def test_all_prices_none(self):
        items = [
            ParsedHolding("RELIANCE", 100, None),
            ParsedHolding("RELIANCE", 50, None),
        ]
        out = collapse_duplicates(items)
        assert out[0].quantity == 150
        assert out[0].avg_price is None

    def test_distinct_tickers_preserved(self):
        items = [
            ParsedHolding("RELIANCE", 100, Decimal("1280")),
            ParsedHolding("TCS", 50, Decimal("2150")),
        ]
        out = collapse_duplicates(items)
        assert {h.ticker for h in out} == {"RELIANCE", "TCS"}
