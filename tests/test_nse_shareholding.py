"""Unit tests for `app.data.sources.nse_shareholding` (pure functions only).

Network paths are exercised by the live integration test in
`scripts/backfill_holdings.py`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.data.sources.nse_shareholding import (
    HoldingRow,
    ShareholdingParseError,
    _parse_dd_mon_yyyy,
    _parse_pct,
    _broadcast_to_date,
    parse_records,
    quarter_label,
)


# ---------------------------------------------------------------------------
# Date / pct parsers
# ---------------------------------------------------------------------------


class TestParseDate:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("31-MAR-2026", date(2026, 3, 31)),
            ("01-jan-2025", date(2025, 1, 1)),
            ("30-Jun-2024", date(2024, 6, 30)),
            ("31-DEC-2023", date(2023, 12, 31)),
        ],
    )
    def test_valid_strings(self, raw: str, expected: date):
        assert _parse_dd_mon_yyyy(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            None,
            "",
            "garbage",
            "31-XYZ-2026",
            "32-MAR-2026",
            "2026-03-31",
            "31/03/2026",
        ],
    )
    def test_invalid_returns_none(self, raw):
        assert _parse_dd_mon_yyyy(raw) is None


class TestParsePct:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("50.01", Decimal("50.01")),
            ("0", Decimal("0")),
            ("100", Decimal("100")),
            ("14.38", Decimal("14.38")),
        ],
    )
    def test_valid(self, raw, expected):
        assert _parse_pct(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "-", "garbage", "  "])
    def test_invalid_returns_none(self, raw):
        assert _parse_pct(raw) is None

    @pytest.mark.parametrize("raw", ["-1", "101", "1000"])
    def test_out_of_range_returns_none(self, raw):
        # Defensive — pct must be 0..100; anything else is garbage.
        assert _parse_pct(raw) is None


class TestBroadcastDate:
    def test_with_time(self):
        assert _broadcast_to_date("21-APR-2026 13:25:14") == date(2026, 4, 21)

    def test_without_time(self):
        assert _broadcast_to_date("21-APR-2026") == date(2026, 4, 21)

    def test_none(self):
        assert _broadcast_to_date(None) is None


# ---------------------------------------------------------------------------
# parse_records
# ---------------------------------------------------------------------------


def _ok_record(date_str: str = "31-MAR-2026", **overrides) -> dict:
    base = {
        "symbol": "RELIANCE",
        "date": date_str,
        "pr_and_prgrp": "50",
        "public_val": "50",
        "employeeTrusts": "0",
        "xbrl": "https://example.com/x.xml",
        "submissionDate": "21-APR-2026",
        "broadcastDate": "21-APR-2026 13:25:14",
    }
    base.update(overrides)
    return base


class TestParseRecords:
    def test_full_payload(self):
        payload = [
            _ok_record("31-MAR-2026", pr_and_prgrp="50", public_val="50"),
            _ok_record("31-DEC-2025", pr_and_prgrp="50.01", public_val="49.99"),
        ]
        rows = parse_records("RELIANCE", payload)
        assert len(rows) == 2
        assert rows[0].quarter_end == date(2026, 3, 31)
        assert rows[0].promoter_pct == Decimal("50")
        assert rows[0].public_pct == Decimal("50")
        assert rows[1].quarter_end == date(2025, 12, 31)
        assert rows[1].promoter_pct == Decimal("50.01")

    def test_ticker_uppercased(self):
        rows = parse_records("reliance", [_ok_record()])
        assert rows[0].ticker == "RELIANCE"

    def test_empty_array_returns_empty(self):
        assert parse_records("RELIANCE", []) == []

    def test_non_list_raises(self):
        with pytest.raises(ShareholdingParseError):
            parse_records("RELIANCE", {"not": "a list"})

    def test_non_dict_rows_skipped(self):
        rows = parse_records("RELIANCE", [_ok_record(), "garbage", 42])
        assert len(rows) == 1

    def test_unparseable_date_skips_row(self):
        rows = parse_records(
            "RELIANCE",
            [_ok_record("garbage-date"), _ok_record("31-MAR-2026")],
        )
        assert len(rows) == 1
        assert rows[0].quarter_end == date(2026, 3, 31)

    def test_missing_pct_fields_become_none(self):
        rows = parse_records(
            "RELIANCE",
            [_ok_record("31-MAR-2026", pr_and_prgrp=None, public_val="-")],
        )
        assert rows[0].promoter_pct is None
        assert rows[0].public_pct is None

    def test_xbrl_url_kept(self):
        rows = parse_records("RELIANCE", [_ok_record(xbrl="https://x.com/y.xml")])
        assert rows[0].xbrl_url == "https://x.com/y.xml"

    def test_xbrl_non_string_dropped(self):
        rows = parse_records("RELIANCE", [_ok_record(xbrl=42)])
        assert rows[0].xbrl_url is None

    def test_raw_record_preserved(self):
        rec = _ok_record(custom_field="hello")
        rows = parse_records("RELIANCE", [rec])
        assert rows[0].raw["custom_field"] == "hello"


# ---------------------------------------------------------------------------
# quarter_label
# ---------------------------------------------------------------------------


class TestQuarterLabel:
    @pytest.mark.parametrize(
        "d,expected",
        [
            (date(2026, 3, 31), "Q4 FY26"),
            (date(2025, 6, 30), "Q1 FY26"),
            (date(2025, 9, 30), "Q2 FY26"),
            (date(2025, 12, 31), "Q3 FY26"),
            (date(2024, 3, 31), "Q4 FY24"),
            (date(2023, 6, 30), "Q1 FY24"),
        ],
    )
    def test_indian_fy_quarters(self, d, expected):
        assert quarter_label(d) == expected

    def test_non_quarter_falls_back_to_iso(self):
        assert quarter_label(date(2026, 5, 15)) == "2026-05-15"
