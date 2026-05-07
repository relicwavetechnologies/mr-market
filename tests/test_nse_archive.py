"""Unit tests for `app.data.sources.nse_archive` — pure functions only.

Network paths are exercised by `tests/test_eod_ingest_live.py` (gated on the
NETWORK_TESTS=1 env var).
"""

from __future__ import annotations

import io
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.sources.nse_archive import (
    BhavcopyParseError,
    BhavRow,
    extract_zip,
    likely_trading_day,
    parse_csv_bytes,
    url_for,
    utc_close_of_day,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bhavcopy_sample.csv"


# ---------------------------------------------------------------------------
# url_for
# ---------------------------------------------------------------------------


class TestUrl:
    def test_zero_padded(self):
        u = url_for(date(2026, 1, 5))
        assert u.endswith("BhavCopy_NSE_CM_0_0_0_20260105_F_0000.csv.zip")

    def test_uses_archive_host(self):
        u = url_for(date(2026, 5, 6))
        assert u.startswith("https://nsearchives.nseindia.com/content/cm/")

    def test_trade_day_round_trip(self):
        d = date(2026, 12, 31)
        assert d.strftime("%Y%m%d") in url_for(d)


# ---------------------------------------------------------------------------
# likely_trading_day
# ---------------------------------------------------------------------------


class TestTradingDay:
    @pytest.mark.parametrize(
        "d,is_trading",
        [
            (date(2026, 5, 4), True),    # Monday
            (date(2026, 5, 5), True),    # Tuesday
            (date(2026, 5, 6), True),    # Wednesday
            (date(2026, 5, 7), True),    # Thursday
            (date(2026, 5, 8), True),    # Friday
            (date(2026, 5, 9), False),   # Saturday
            (date(2026, 5, 10), False),  # Sunday
        ],
    )
    def test_weekend_filter(self, d: date, is_trading: bool):
        assert likely_trading_day(d) is is_trading


# ---------------------------------------------------------------------------
# utc_close_of_day
# ---------------------------------------------------------------------------


class TestUtcClose:
    def test_returns_10utc(self):
        ts = utc_close_of_day(date(2026, 5, 6))
        assert ts.year == 2026 and ts.month == 5 and ts.day == 6
        assert ts.hour == 10 and ts.minute == 0
        assert ts.tzinfo is not None
        assert ts.utcoffset().total_seconds() == 0


# ---------------------------------------------------------------------------
# parse_csv_bytes
# ---------------------------------------------------------------------------


def _fixture_bytes() -> bytes:
    return FIXTURE.read_bytes()


class TestParse:
    def test_fixture_loads(self):
        rows = parse_csv_bytes(_fixture_bytes())
        assert rows, "fixture should contain at least one EQ row"
        for r in rows:
            assert isinstance(r, BhavRow)
            assert r.ticker.isupper()
            assert isinstance(r.close, Decimal)
            assert r.trade_date == date(2026, 5, 6)

    def test_universe_filter(self):
        rows = parse_csv_bytes(
            _fixture_bytes(),
            universe={"20MICRONS", "DOES_NOT_EXIST"},
        )
        # The fixture starts at "20MICRONS" alphabetically — should be present.
        assert len(rows) == 1
        assert rows[0].ticker == "20MICRONS"

    def test_universe_case_insensitive(self):
        rows = parse_csv_bytes(_fixture_bytes(), universe={"20microns"})
        assert len(rows) == 1
        assert rows[0].ticker == "20MICRONS"

    def test_empty_universe_skips_all(self):
        rows = parse_csv_bytes(_fixture_bytes(), universe=set())
        assert rows == []

    def test_decimal_precision_preserved(self):
        rows = parse_csv_bytes(_fixture_bytes(), universe={"20MICRONS"})
        r = rows[0]
        # Fixture row: 182.40,184.13,178.00,182.32,...,180.25
        assert r.open == Decimal("182.40")
        assert r.high == Decimal("184.13")
        assert r.low == Decimal("178.00")
        assert r.close == Decimal("182.32")
        assert r.prev_close == Decimal("180.25")

    def test_volume_int(self):
        rows = parse_csv_bytes(_fixture_bytes(), universe={"20MICRONS"})
        assert rows[0].volume == 109136

    def test_skips_non_eq_series(self):
        # Inject a bond row with the same TckrSymb but SctySrs=GB
        body = _fixture_bytes() + b"\n" + (
            b"2026-05-06,2026-05-06,CM,NSE,STK,1234,IN0000000000,FAKE,GB,,,,,Fake Bond,"
            b"100.00,101.00,99.00,100.50,100.50,99.50,,100.50,,,1000,100000.00,10,F1,1,,,,,"
        )
        rows = parse_csv_bytes(body, universe={"FAKE"})
        assert rows == [], "GB-series row should be filtered out"

    def test_skips_empty_close(self):
        body = (
            b"TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,"
            b"FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,"
            b"LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,"
            b"TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4\n"
            b"2026-05-06,2026-05-06,CM,NSE,STK,1,X,FOO,EQ,,,,,Foo,100,101,99,,,99.5,,,,,1000,100000,10,F1,1,,,,,"
        )
        rows = parse_csv_bytes(body)
        # Empty close → row must be skipped
        assert rows == []

    def test_missing_required_column_raises(self):
        # Drop ClsPric from the header — required → must raise
        body = (
            b"TradDt,TckrSymb,SctySrs,OpnPric\n"
            b"2026-05-06,FOO,EQ,100\n"
        )
        with pytest.raises(BhavcopyParseError) as exc:
            parse_csv_bytes(body)
        assert "missing columns" in str(exc.value)

    def test_empty_body_raises(self):
        with pytest.raises(BhavcopyParseError):
            parse_csv_bytes(b"")

    def test_bad_date_skips_row_not_aborts_file(self):
        body = (
            b"TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,"
            b"FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,"
            b"LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,"
            b"TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4\n"
            b"NOT-A-DATE,2026-05-06,CM,NSE,STK,1,X,BAD,EQ,,,,,Bad,1,1,1,1,1,1,,,,,,,,,F1,1,,,,,\n"
            b"2026-05-06,2026-05-06,CM,NSE,STK,2,Y,GOOD,EQ,,,,,Good,100,101,99,100.5,100.5,99.5,,,,,1000,100000,10,F1,1,,,,,"
        )
        rows = parse_csv_bytes(body)
        # Only the GOOD row survives — bad-date row was skipped, not aborted
        assert len(rows) == 1
        assert rows[0].ticker == "GOOD"


# ---------------------------------------------------------------------------
# extract_zip
# ---------------------------------------------------------------------------


class TestExtractZip:
    def _make_zip(self, members: dict[str, bytes]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in members.items():
                zf.writestr(name, data)
        return buf.getvalue()

    def test_single_csv_round_trip(self):
        body = b"TradDt,Foo\n2026-05-06,1\n"
        zb = self._make_zip({"x.csv": body})
        assert extract_zip(zb) == body

    def test_picks_csv_among_others(self):
        zb = self._make_zip({"meta.txt": b"junk", "data.csv": b"hello"})
        assert extract_zip(zb) == b"hello"

    def test_no_csv_raises(self):
        zb = self._make_zip({"data.txt": b"not csv"})
        with pytest.raises(BhavcopyParseError):
            extract_zip(zb)

    def test_bad_zip_raises(self):
        with pytest.raises(BhavcopyParseError):
            extract_zip(b"not a zip")
