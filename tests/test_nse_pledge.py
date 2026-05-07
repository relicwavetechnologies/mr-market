"""Pure-parser tests for the NSE pledge endpoint (D8).

Network is mocked; we only exercise `parse_records` against canned NSE
JSON shapes plus the small risk-band helper.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.data.sources.nse_pledge import _band, parse_records


# ---------------------------------------------------------------------------
# Risk band thresholds
# ---------------------------------------------------------------------------


class TestRiskBand:
    def test_none_pledged_is_unknown(self):
        assert _band(None) == "unknown"

    def test_under_5pct_is_low(self):
        assert _band(Decimal("0")) == "low"
        assert _band(Decimal("1.08")) == "low"
        assert _band(Decimal("4.99")) == "low"

    def test_5_to_10_is_moderate(self):
        assert _band(Decimal("5")) == "moderate"
        assert _band(Decimal("9.99")) == "moderate"

    def test_10_to_25_is_elevated(self):
        assert _band(Decimal("10")) == "elevated"
        assert _band(Decimal("18.5")) == "elevated"
        assert _band(Decimal("24.99")) == "elevated"

    def test_25_or_more_is_high(self):
        assert _band(Decimal("25")) == "high"
        assert _band(Decimal("60.4")) == "high"
        assert _band(Decimal("100")) == "high"


# ---------------------------------------------------------------------------
# parse_records — happy path against real Reliance shape
# ---------------------------------------------------------------------------


class TestParseRecords:
    def test_real_reliance_payload_shape(self):
        payload = {
            "comNameList": ["Reliance Industries Limited"],
            "data": [
                {
                    "comName": "Reliance Industries Limited",
                    "shp": "31-Mar-2026",
                    "totIssuedShares": "13532472634",
                    "totPromoterHolding": "6886783924",
                    "percPromoterHolding": "    50.89",
                    "totPublicHolding": "6645688710",
                    "totPromoterShares": "0",
                    "percPromoterShares": "     0.00",
                    "percTotShares": "     0.00",
                    "numSharesPledged": "146050495",
                    "totDematShares": "13502811397",
                    "sharesCollateral": "0",
                    "nbfcPromoShare": "0",
                    "nbfcNonPromoShare": "0",
                    "percSharesPledged": "1.08",
                    "broadcastDt": "07-May-2026 16:30:21",
                    "disclosureFromDate": None,
                    "disclosureToDate": None,
                    "compBroadcastDate": None,
                    "noOfPledgeShare": "0",
                    "noOfSecPledgeShare": "19627.726",
                }
            ],
        }
        rows = parse_records("RELIANCE", payload)
        assert len(rows) == 1
        r = rows[0]
        assert r.ticker == "RELIANCE"
        assert r.quarter_end == date(2026, 3, 31)
        assert r.promoter_pct == Decimal("50.89")
        assert r.pledged_pct == Decimal("1.08")
        assert r.num_shares_pledged == 146_050_495
        assert r.total_promoter_shares == 6_886_783_924
        assert r.total_issued_shares == 13_532_472_634
        assert r.broadcast_at == datetime(2026, 5, 7, 16, 30, 21)
        assert r.risk_band == "low"

    def test_multiple_quarters_sorted_latest_first(self):
        payload = {
            "data": [
                {"shp": "31-Mar-2024", "percSharesPledged": "8.0"},
                {"shp": "31-Mar-2026", "percSharesPledged": "1.08"},
                {"shp": "31-Mar-2025", "percSharesPledged": "12.5"},
            ]
        }
        rows = parse_records("X", payload)
        assert [r.quarter_end.year for r in rows] == [2026, 2025, 2024]
        assert [r.risk_band for r in rows] == ["low", "elevated", "moderate"]

    def test_high_risk_pledge(self):
        payload = {"data": [{"shp": "31-Dec-2025", "percSharesPledged": "62.4"}]}
        rows = parse_records("X", payload)
        assert rows[0].risk_band == "high"
        assert rows[0].pledged_pct == Decimal("62.4")

    def test_missing_pledge_pct_keeps_row_with_unknown_band(self):
        payload = {"data": [{"shp": "30-Sep-2025", "percSharesPledged": None}]}
        rows = parse_records("X", payload)
        assert len(rows) == 1
        assert rows[0].pledged_pct is None
        assert rows[0].risk_band == "unknown"

    def test_dropped_rows_with_unparseable_quarter(self):
        payload = {
            "data": [
                {"shp": "garbage-date", "percSharesPledged": "5.0"},
                {"shp": "30-Jun-2025", "percSharesPledged": "5.0"},
            ]
        }
        rows = parse_records("X", payload)
        assert len(rows) == 1
        assert rows[0].quarter_end == date(2025, 6, 30)


# ---------------------------------------------------------------------------
# parse_records — defensive / edge cases
# ---------------------------------------------------------------------------


class TestParseDefensive:
    def test_non_dict_payload_returns_empty(self):
        assert parse_records("X", "not a dict") == []
        assert parse_records("X", None) == []
        assert parse_records("X", [1, 2, 3]) == []

    def test_payload_without_data_key_returns_empty(self):
        assert parse_records("X", {"comNameList": ["X"]}) == []

    def test_data_not_a_list_returns_empty(self):
        assert parse_records("X", {"data": "oops"}) == []

    def test_non_dict_items_dropped(self):
        payload = {"data": [None, "string", 42, {"shp": "30-Jun-2025"}]}
        rows = parse_records("X", payload)
        assert len(rows) == 1

    def test_pct_out_of_range_treated_as_missing(self):
        # NSE has been seen to return -1 or > 100 on bad filings — drop those.
        payload = {"data": [{"shp": "30-Jun-2025", "percSharesPledged": "150"}]}
        rows = parse_records("X", payload)
        assert rows[0].pledged_pct is None
        assert rows[0].risk_band == "unknown"

    def test_int_with_commas_parsed(self):
        payload = {
            "data": [
                {
                    "shp": "30-Jun-2025",
                    "numSharesPledged": "1,234,567",
                }
            ]
        }
        rows = parse_records("X", payload)
        assert rows[0].num_shares_pledged == 1_234_567

    def test_broadcast_with_date_only(self):
        payload = {"data": [{"shp": "30-Jun-2025", "broadcastDt": "01-Jul-2025"}]}
        rows = parse_records("X", payload)
        assert rows[0].broadcast_at == datetime(2025, 7, 1)

    def test_ticker_is_upper_cased(self):
        payload = {"data": [{"shp": "30-Jun-2025"}]}
        rows = parse_records("reliance", payload)
        assert rows[0].ticker == "RELIANCE"
