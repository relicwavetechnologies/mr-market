"""Unit tests for `app.data.sources.nse_deals` (pure functions)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from app.data.sources.nse_deals import (
    DealRow,
    DealsParseError,
    _normalise_side,
    _parse_decimal,
    _parse_dd_mon_yyyy,
    _parse_int,
    parse_dataframe,
)


# ---------------------------------------------------------------------------
# Lower-level parsers
# ---------------------------------------------------------------------------


class TestParseDate:
    def test_canonical(self):
        assert _parse_dd_mon_yyyy("07-MAY-2026") == date(2026, 5, 7)

    def test_lowercase(self):
        assert _parse_dd_mon_yyyy("07-may-2026") == date(2026, 5, 7)

    @pytest.mark.parametrize("s", [None, "", "garbage", "07-XYZ-2026", "32-MAY-2026", "2026-05-07"])
    def test_invalid(self, s):
        assert _parse_dd_mon_yyyy(s) is None


class TestParseInt:
    @pytest.mark.parametrize(
        "raw,expected",
        [("12345", 12345), ("12,345", 12345), ("5,70,000", 570000), ("0", 0), ("12345.0", 12345)],
    )
    def test_valid(self, raw, expected):
        assert _parse_int(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "  ", "garbage"])
    def test_invalid(self, raw):
        assert _parse_int(raw) is None


class TestParseDecimal:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("442.00", Decimal("442.00")),
            ("1,436.20", Decimal("1436.20")),
            ("0.50", Decimal("0.50")),
        ],
    )
    def test_valid(self, raw, expected):
        assert _parse_decimal(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "-", "garbage"])
    def test_invalid(self, raw):
        assert _parse_decimal(raw) is None


class TestNormaliseSide:
    @pytest.mark.parametrize(
        "raw,expected",
        [("BUY", "BUY"), ("Buy", "BUY"), ("B", "BUY"),
         ("SELL", "SELL"), ("sell", "SELL"), ("S", "SELL"),
         ("  buy  ", "BUY")],
    )
    def test_normalises(self, raw, expected):
        assert _normalise_side(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "MAYBE", "TRADE"])
    def test_invalid_returns_none(self, raw):
        assert _normalise_side(raw) is None


# ---------------------------------------------------------------------------
# parse_dataframe
# ---------------------------------------------------------------------------


def _frame(rows: list[dict]) -> pd.DataFrame:
    """Build a frame matching nselib's column shape."""
    return pd.DataFrame(rows)


def _good_row(**overrides) -> dict:
    base = {
        "Date": "08-APR-2026",
        "Symbol": "DELHIVERY",
        "SecurityName": "Delhivery Limited",
        "ClientName": "ALPHAMINE ABSOLUTE RETURN FUND",
        "Buy/Sell": "BUY",
        "QuantityTraded": "5,70,000",
        "TradePrice/Wght.Avg.Price": "442.00",
        "Remarks": "-",
    }
    base.update(overrides)
    return base


class TestParseDataframe:
    def test_full_payload(self):
        df = _frame([_good_row(), _good_row(Symbol="RELIANCE", **{"Buy/Sell": "SELL"})])
        rows = parse_dataframe(df, kind="block")
        assert len(rows) == 2
        assert rows[0].symbol == "DELHIVERY" and rows[0].side == "BUY"
        assert rows[0].quantity == 570000
        assert rows[0].avg_price == Decimal("442.00")
        assert rows[0].kind == "block"
        assert rows[1].side == "SELL"

    def test_empty_frame(self):
        assert parse_dataframe(pd.DataFrame(), kind="bulk") == []

    def test_none_frame(self):
        assert parse_dataframe(None, kind="bulk") == []  # type: ignore[arg-type]

    def test_missing_required_column_raises(self):
        df = _frame([{"Date": "07-MAY-2026", "Symbol": "X"}])
        with pytest.raises(DealsParseError):
            parse_dataframe(df, kind="bulk")

    def test_skips_bad_date(self):
        df = _frame([_good_row(Date="garbage"), _good_row(Symbol="OK")])
        rows = parse_dataframe(df, kind="bulk")
        assert len(rows) == 1
        assert rows[0].symbol == "OK"

    def test_skips_blank_symbol(self):
        df = _frame([_good_row(Symbol=""), _good_row()])
        rows = parse_dataframe(df, kind="bulk")
        assert len(rows) == 1
        assert rows[0].symbol == "DELHIVERY"

    def test_skips_unknown_side(self):
        df = _frame([_good_row(**{"Buy/Sell": "MAYBE"}), _good_row()])
        rows = parse_dataframe(df, kind="bulk")
        assert len(rows) == 1

    def test_skips_zero_or_negative_qty(self):
        df = _frame([
            _good_row(QuantityTraded="0"),
            _good_row(QuantityTraded="-5"),
            _good_row(),
        ])
        rows = parse_dataframe(df, kind="bulk")
        assert len(rows) == 1

    def test_skips_zero_price(self):
        df = _frame([_good_row(**{"TradePrice/Wght.Avg.Price": "0"}), _good_row()])
        rows = parse_dataframe(df, kind="bulk")
        assert len(rows) == 1

    def test_remarks_dash_and_nan_become_none(self):
        df = _frame([
            _good_row(Remarks="-"),
            _good_row(Remarks="nan"),
            _good_row(Remarks=None),
            _good_row(Remarks="actual remark"),
        ])
        rows = parse_dataframe(df, kind="bulk")
        assert len(rows) == 4
        assert rows[0].remarks is None
        assert rows[1].remarks is None
        assert rows[2].remarks is None
        assert rows[3].remarks == "actual remark"

    def test_kind_propagated(self):
        df = _frame([_good_row()])
        for k in ("bulk", "block"):
            rows = parse_dataframe(df, kind=k)  # type: ignore[arg-type]
            assert rows[0].kind == k

    def test_symbol_uppercased(self):
        df = _frame([_good_row(Symbol="reliance")])
        rows = parse_dataframe(df, kind="bulk")
        assert rows[0].symbol == "RELIANCE"


# ---------------------------------------------------------------------------
# Worker dedupe (pure)
# ---------------------------------------------------------------------------


class TestDedupe:
    def test_collapses_exact_duplicates(self):
        from app.workers.deals_ingest import _dedupe_natural_key

        r = DealRow(
            trade_date=date(2026, 5, 7),
            symbol="RELIANCE",
            security_name="Reliance Industries Limited",
            client_name="X FUND",
            side="BUY",
            quantity=100000,
            avg_price=Decimal("1436.20"),
            remarks=None,
            kind="bulk",
        )
        out = _dedupe_natural_key([r, r, r])
        assert len(out) == 1

    def test_keeps_distinct_rows(self):
        from app.workers.deals_ingest import _dedupe_natural_key

        r1 = DealRow(
            trade_date=date(2026, 5, 7),
            symbol="RELIANCE",
            security_name="Reliance Industries Limited",
            client_name="X FUND",
            side="BUY",
            quantity=100000,
            avg_price=Decimal("1436.20"),
            remarks=None,
            kind="bulk",
        )
        r2 = DealRow(
            trade_date=date(2026, 5, 7),
            symbol="RELIANCE",
            security_name="Reliance Industries Limited",
            client_name="X FUND",
            side="SELL",   # different side
            quantity=100000,
            avg_price=Decimal("1436.20"),
            remarks=None,
            kind="bulk",
        )
        out = _dedupe_natural_key([r1, r2])
        assert len(out) == 2
