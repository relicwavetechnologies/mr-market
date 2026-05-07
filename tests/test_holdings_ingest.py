"""Unit tests for `app.workers.holdings_ingest._dedupe_keep_latest`."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.data.sources.nse_shareholding import HoldingRow
from app.workers.holdings_ingest import _dedupe_keep_latest


def _row(
    quarter: date,
    *,
    promoter: str = "50",
    broadcast: date | None = None,
    submission: date | None = None,
    raw_tag: str = "",
) -> HoldingRow:
    return HoldingRow(
        ticker="RELIANCE",
        quarter_end=quarter,
        promoter_pct=Decimal(promoter),
        public_pct=Decimal("50"),
        employee_trust_pct=Decimal("0"),
        xbrl_url=None,
        submission_date=submission,
        broadcast_date=broadcast,
        raw={"tag": raw_tag},
    )


class TestDedupe:
    def test_no_duplicates_returns_all(self):
        rows = [
            _row(date(2026, 3, 31), broadcast=date(2026, 4, 21), raw_tag="a"),
            _row(date(2025, 12, 31), broadcast=date(2026, 1, 21), raw_tag="b"),
        ]
        out = _dedupe_keep_latest(rows)
        assert len(out) == 2

    def test_duplicates_keep_latest_broadcast(self):
        rows = [
            _row(
                date(2026, 3, 31),
                broadcast=date(2026, 4, 21),
                raw_tag="original",
            ),
            _row(
                date(2026, 3, 31),
                broadcast=date(2026, 4, 25),       # revised, later broadcast
                raw_tag="revised",
                promoter="50.5",
            ),
        ]
        out = _dedupe_keep_latest(rows)
        assert len(out) == 1
        assert out[0].raw["tag"] == "revised"
        assert out[0].promoter_pct == Decimal("50.5")

    def test_falls_back_to_submission_when_broadcast_missing(self):
        rows = [
            _row(date(2026, 3, 31), broadcast=None, submission=date(2026, 4, 21), raw_tag="first"),
            _row(date(2026, 3, 31), broadcast=None, submission=date(2026, 4, 25), raw_tag="latest"),
        ]
        out = _dedupe_keep_latest(rows)
        assert out[0].raw["tag"] == "latest"

    def test_empty_input(self):
        assert _dedupe_keep_latest([]) == []

    def test_keeps_first_when_both_lack_dates(self):
        # Tie-breakers: if both rows lack broadcast/submission, the first wins.
        a = _row(date(2026, 3, 31), broadcast=None, submission=None, raw_tag="a")
        b = _row(date(2026, 3, 31), broadcast=None, submission=None, raw_tag="b")
        out = _dedupe_keep_latest([a, b])
        assert len(out) == 1
        assert out[0].raw["tag"] == "a"

    def test_three_revisions_keeps_newest(self):
        rows = [
            _row(date(2026, 3, 31), broadcast=date(2026, 4, 21), raw_tag="v1"),
            _row(date(2026, 3, 31), broadcast=date(2026, 4, 25), raw_tag="v2"),
            _row(date(2026, 3, 31), broadcast=date(2026, 5, 1), raw_tag="v3"),
        ]
        out = _dedupe_keep_latest(rows)
        assert len(out) == 1
        assert out[0].raw["tag"] == "v3"
