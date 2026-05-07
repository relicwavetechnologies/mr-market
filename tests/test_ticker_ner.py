"""Ticker NER tests — pure function on `_build_index` (no DB)."""

from __future__ import annotations

from app.analytics.ticker_ner import _build_index


class _FakeStock:
    __slots__ = ("ticker", "name", "active")

    def __init__(self, ticker: str, name: str) -> None:
        self.ticker = ticker
        self.name = name
        self.active = True


def _idx_for(*pairs: tuple[str, str]):
    return _build_index([_FakeStock(t, n) for t, n in pairs])


def test_finds_single_alias():
    idx = _idx_for(("RELIANCE", "Reliance Industries Ltd"))
    assert idx.find_tickers("Reliance Industries posts record Q4") == ["RELIANCE"]


def test_short_uppercase_symbol_match():
    idx = _idx_for(("TCS", "Tata Consultancy Services Ltd"))
    assert idx.find_tickers("TCS announces buyback") == ["TCS"]
    assert idx.find_tickers("Tata Consultancy beats estimates") == ["TCS"]


def test_multiple_tickers_in_one_headline():
    idx = _idx_for(
        ("RELIANCE", "Reliance Industries Ltd"),
        ("TCS", "Tata Consultancy Services Ltd"),
    )
    out = idx.find_tickers("Reliance and TCS lead Nifty gainers today")
    assert set(out) == {"RELIANCE", "TCS"}


def test_dedupe_repeated_mentions():
    idx = _idx_for(("INFY", "Infosys Ltd"))
    out = idx.find_tickers("Infosys, Infosys, Infosys: triple coverage")
    assert out == ["INFY"]


def test_word_boundary_no_substring_match():
    # "Infy" appears in "infydsfdsfds" — should NOT match
    idx = _idx_for(("INFY", "Infosys Ltd"))
    assert idx.find_tickers("Infydsfds is a fake word") == []


def test_longer_alias_wins_over_shorter():
    # "Tata Motors" should resolve to TATAMOTORS even if "tata" alone could
    # match another ticker like TATASTEEL (TATA appears in both names).
    idx = _idx_for(
        ("TATAMOTORS", "Tata Motors Ltd"),
        ("TATASTEEL", "Tata Steel Ltd"),
    )
    out = idx.find_tickers("Tata Motors posts record Q4 profit")
    assert "TATAMOTORS" in out


def test_case_insensitive():
    idx = _idx_for(("RELIANCE", "Reliance Industries Ltd"))
    assert idx.find_tickers("RELIANCE INDUSTRIES POSTS Q4") == ["RELIANCE"]
    assert idx.find_tickers("reliance industries posts q4") == ["RELIANCE"]


def test_empty_text():
    idx = _idx_for(("RELIANCE", "Reliance Industries Ltd"))
    assert idx.find_tickers("") == []
    assert idx.find_tickers("   ") == []


def test_no_match_returns_empty():
    idx = _idx_for(("RELIANCE", "Reliance Industries Ltd"))
    assert idx.find_tickers("The weather today is nice") == []
