"""Unit tests for the NIFTY-100 universe seed (P3-A1).

We exercise the pure-functional pieces of `scripts.seed_universe` (CSV
parsing) plus structural invariants on the shipped CSVs themselves
(no duplicates, exactly 100 NIFTY-100 / 50 NIFTY-50 rows, every column
populated where required, NIFTY-50 ⊂ NIFTY-100). Network and Postgres
are NOT touched here — the scrape backfill is exercised by the live
`scripts.backfill_*` runs documented in the run book.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.seed_universe import UNIVERSES, parse_csv

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NIFTY50 = DATA_DIR / "nifty50.csv"
NIFTY100 = DATA_DIR / "nifty100.csv"


# ---------------------------------------------------------------------------
# CSV file shape + content invariants
# ---------------------------------------------------------------------------


class TestNifty100CsvShape:
    def test_file_exists(self):
        assert NIFTY100.exists(), f"missing universe file: {NIFTY100}"

    def test_exactly_100_rows(self):
        with NIFTY100.open() as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 100, f"NIFTY-100 must have 100 rows, got {len(rows)}"

    def test_no_duplicate_tickers(self):
        with NIFTY100.open() as f:
            tickers = [r["ticker"].strip() for r in csv.DictReader(f)]
        assert len(set(tickers)) == len(tickers), (
            f"duplicate tickers: {sorted(t for t in tickers if tickers.count(t) > 1)}"
        )

    def test_all_required_columns_populated(self):
        required = {"ticker", "exchange", "yahoo_symbol", "name"}
        with NIFTY100.open() as f:
            for r in csv.DictReader(f):
                missing = [c for c in required if not r.get(c, "").strip()]
                assert not missing, f"row {r['ticker']!r} missing: {missing}"

    def test_yahoo_symbol_matches_ticker_pattern(self):
        # Yahoo URL-encodes special characters in tickers (e.g. M&M → M%26M.NS).
        from urllib.parse import unquote

        with NIFTY100.open() as f:
            for r in csv.DictReader(f):
                t = r["ticker"].strip()
                y = r["yahoo_symbol"].strip()
                assert y.endswith(".NS"), f"{t}: yahoo_symbol {y!r} not .NS-suffixed"
                decoded = unquote(y[:-3])
                assert decoded == t, (
                    f"{t}: yahoo_symbol {y!r} (decoded {decoded!r}) doesn't match ticker"
                )

    def test_exchange_is_nse(self):
        with NIFTY100.open() as f:
            for r in csv.DictReader(f):
                assert r["exchange"].strip() == "NSE", (
                    f"{r['ticker']}: unexpected exchange {r['exchange']!r}"
                )

    def test_every_row_has_sector(self):
        # We don't enforce sector is required but we want zero blank
        # sectors in a NIFTY-100 sweep — gaps cause holes in the
        # screener / sector-concentration tools downstream.
        with NIFTY100.open() as f:
            blanks = [r["ticker"] for r in csv.DictReader(f) if not r.get("sector", "").strip()]
        assert not blanks, f"tickers with blank sector: {blanks}"


# ---------------------------------------------------------------------------
# NIFTY-50 still ships, NIFTY-50 ⊂ NIFTY-100
# ---------------------------------------------------------------------------


class TestNifty50Compat:
    def test_legacy_nifty50_file_still_present(self):
        assert NIFTY50.exists(), (
            "NIFTY-50 file removed — keep it for rate-limit fallback ops"
        )

    def test_nifty50_has_50_unique_tickers(self):
        with NIFTY50.open() as f:
            tickers = [r["ticker"].strip() for r in csv.DictReader(f)]
        assert len(tickers) == 50
        assert len(set(tickers)) == 50

    def test_nifty50_is_strict_subset_of_nifty100(self):
        with NIFTY50.open() as f:
            n50 = {r["ticker"].strip() for r in csv.DictReader(f)}
        with NIFTY100.open() as f:
            n100 = {r["ticker"].strip() for r in csv.DictReader(f)}
        missing = n50 - n100
        assert not missing, f"NIFTY-50 tickers not in NIFTY-100: {sorted(missing)}"

    def test_50_new_tickers_in_nifty100(self):
        """NIFTY-100 = NIFTY-50 + exactly 50 new tickers."""
        with NIFTY50.open() as f:
            n50 = {r["ticker"].strip() for r in csv.DictReader(f)}
        with NIFTY100.open() as f:
            n100 = {r["ticker"].strip() for r in csv.DictReader(f)}
        new_tickers = n100 - n50
        assert len(new_tickers) == 50, (
            f"expected 50 new tickers, got {len(new_tickers)}: {sorted(new_tickers)}"
        )


# ---------------------------------------------------------------------------
# parse_csv — pure function tests
# ---------------------------------------------------------------------------


class TestParseCsv:
    def test_parses_nifty100_into_100_dicts(self):
        rows = parse_csv(NIFTY100)
        assert len(rows) == 100
        assert all(set(r.keys()) >= {"ticker", "name", "exchange", "yahoo_symbol", "active"} for r in rows)

    def test_active_defaults_true(self):
        rows = parse_csv(NIFTY100)
        assert all(r["active"] is True for r in rows)

    def test_blank_optional_fields_become_none(self, tmp_path: Path):
        csv_path = tmp_path / "tiny.csv"
        csv_path.write_text(
            "ticker,exchange,yahoo_symbol,name,sector,industry\n"
            "FOO,NSE,FOO.NS,Foo Ltd,,\n"
        )
        rows = parse_csv(csv_path)
        assert rows == [
            {
                "ticker": "FOO",
                "exchange": "NSE",
                "yahoo_symbol": "FOO.NS",
                "name": "Foo Ltd",
                "sector": None,
                "industry": None,
                "active": True,
            }
        ]

    def test_strips_whitespace(self, tmp_path: Path):
        csv_path = tmp_path / "ws.csv"
        csv_path.write_text(
            "ticker,exchange,yahoo_symbol,name,sector,industry\n"
            "  FOO  ,NSE,FOO.NS, Foo Ltd ,Tech ,Software\n"
        )
        rows = parse_csv(csv_path)
        assert rows[0]["ticker"] == "FOO"
        assert rows[0]["name"] == "Foo Ltd"
        assert rows[0]["sector"] == "Tech"

    def test_unknown_path_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            parse_csv(tmp_path / "missing.csv")


# ---------------------------------------------------------------------------
# UNIVERSES dict — wired correctly
# ---------------------------------------------------------------------------


class TestUniversesDict:
    def test_nifty50_and_nifty100_registered(self):
        assert "nifty50" in UNIVERSES
        assert "nifty100" in UNIVERSES

    def test_paths_resolve_to_data_dir(self):
        assert UNIVERSES["nifty50"].name == "nifty50.csv"
        assert UNIVERSES["nifty100"].name == "nifty100.csv"

    def test_both_paths_exist_on_disk(self):
        for name, p in UNIVERSES.items():
            assert p.exists(), f"universe {name!r} CSV missing at {p}"


# ---------------------------------------------------------------------------
# Sector coverage — the screener / portfolio diagnostics need diversity
# ---------------------------------------------------------------------------


class TestSectorCoverage:
    def test_at_least_8_distinct_sectors(self):
        rows = parse_csv(NIFTY100)
        sectors = {r["sector"] for r in rows if r["sector"]}
        assert len(sectors) >= 8, f"thin sector coverage: {sorted(sectors)}"

    def test_no_single_sector_exceeds_30_percent(self):
        """Concentration sanity — protects PortfolioCard from misleading
        sector breakdowns out of the box."""
        from collections import Counter

        rows = parse_csv(NIFTY100)
        counts = Counter(r["sector"] for r in rows if r["sector"])
        if not counts:
            return
        most_common, n = counts.most_common(1)[0]
        assert n / len(rows) <= 0.30, (
            f"sector {most_common!r} has {n}/100 = {n}% — over 30% concentration"
        )
