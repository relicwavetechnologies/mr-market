"""Sentiment scoring smoke tests (VADER, no model download)."""

from __future__ import annotations

from decimal import Decimal

from app.analytics.sentiment import score


def test_clearly_positive():
    # VADER is general-English (not finance-tuned). Use words in its lexicon.
    r = score("Reliance shares surge with great results and strong buy ratings")
    assert r.label == "positive"
    assert r.score > Decimal("0.05")


def test_clearly_negative():
    r = score("Tata Motors plummets on terrible results and disappointing outlook")
    assert r.label == "negative"
    assert r.score < Decimal("-0.05")


def test_neutral_no_polarity():
    r = score("HDFC Bank to host Q4 results conference call on Friday")
    assert r.label == "neutral"
    assert -Decimal("0.05") <= r.score <= Decimal("0.05")


def test_empty_input():
    r = score("")
    assert r.label == "neutral"
    assert r.score == Decimal(0)


def test_whitespace_input():
    r = score("    \n  ")
    assert r.label == "neutral"
    assert r.score == Decimal(0)
