"""Unit tests for the SEBI safe-harbour guardrails (pure functions)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.analytics.ticker_ner import _build_index
from app.llm.guardrails import (
    apply_guardrails,
    collect_truth_set,
    extract_numbers,
    find_blocklist_hits,
    maybe_inject_disclaimer,
    verify_claims,
)
from app.llm.prompts import INLINE_DISCLAIMER


# ---------------------------------------------------------------------------
# Layer 1 — blocklist
# ---------------------------------------------------------------------------

class TestBlocklistRecommendations:
    @pytest.mark.parametrize(
        "phrase",
        [
            "you should buy Reliance",
            "I recommend buying TCS",
            "we advise selling Adani",
            "must exit Infosys",
            "you should accumulate at the dip",
        ],
    )
    def test_recommendation_verbs_caught(self, phrase: str):
        hits = find_blocklist_hits(phrase)
        assert hits, f"expected blocklist hit for: {phrase}"
        assert any(h.category == "recommendation" for h in hits)

    def test_buy_at_level_caught(self):
        hits = find_blocklist_hits("Reliance is attractive — buy at ₹1400")
        assert any(h.rule_id == "rec_buy_at" for h in hits)

    def test_book_profit_caught(self):
        hits = find_blocklist_hits("you can book your profit at this level")
        assert any(h.rule_id == "rec_book_profit" for h in hits)

    def test_load_up_caught(self):
        hits = find_blocklist_hits("This is a great time to load up.")
        assert any(h.rule_id == "rec_load_up" for h in hits)


class TestBlocklistTargets:
    def test_price_target_caught(self):
        hits = find_blocklist_hits("Brokerages set a target of ₹1,800 on Reliance")
        assert any(h.category == "target" for h in hits)

    def test_fair_value_caught(self):
        hits = find_blocklist_hits("My fair value of ₹1500 means it's undervalued")
        assert any(h.rule_id == "tgt_fair_value" for h in hits)

    def test_upside_caught(self):
        hits = find_blocklist_hits("There's 25% upside from current levels")
        assert any(h.rule_id == "tgt_upside" for h in hits)


class TestBlocklistStopLossEntry:
    def test_stop_loss_at_caught(self):
        hits = find_blocklist_hits("Place a stop-loss at ₹1300")
        assert any(h.category == "stop_loss" for h in hits)

    def test_sl_short_form_caught(self):
        hits = find_blocklist_hits("SL at 1290 should protect downside")
        assert any(h.rule_id == "sl_short" for h in hits)

    def test_entry_at_caught(self):
        hits = find_blocklist_hits("Entry at ₹1430 looks good")
        assert any(h.rule_id == "entry_at" for h in hits)


class TestBlocklistFno:
    def test_options_strategy_caught(self):
        hits = find_blocklist_hits("Try a bull call spread on Bank Nifty")
        assert any(h.category == "fno" for h in hits)

    def test_intraday_setup_caught(self):
        hits = find_blocklist_hits("Intraday long on HDFC Bank looks promising")
        assert any(h.rule_id == "fno_intraday" for h in hits)


class TestBlocklistFalsePositives:
    @pytest.mark.parametrize(
        "phrase",
        [
            "Reliance is at ₹1436. Day range ₹1430.30–₹1449.50.",
            "TCS is in the IT sector with a P/E of 24.07.",
            "The P/E ratio measures price relative to earnings per share.",
            "Infosys reported revenue growth of 8% in Q4.",
            "RELIANCE 52-week range: ₹1290–₹1612.",
            "Buyout speculation around the company.",  # 'buy' substring without word boundary should NOT match
        ],
    )
    def test_factual_phrases_pass(self, phrase: str):
        hits = find_blocklist_hits(phrase)
        assert hits == [], f"unexpected blocklist hit: {[h.rule_id for h in hits]} on: {phrase}"


# ---------------------------------------------------------------------------
# Layer 2 — number extraction & verifier
# ---------------------------------------------------------------------------

class TestExtractNumbers:
    def test_finds_decimals_and_percents(self):
        nums = extract_numbers("Price ₹1436.20, change -0.16%, P/E 24.07")
        values = [str(n.value) for n in nums]
        assert "1436.20" in values
        assert "-0.16" in values or "0.16" in values  # sign may go to either capture
        assert "24.07" in values

    def test_handles_indian_lakh_separators(self):
        nums = extract_numbers("Market cap ₹19,43,610 Cr")
        # 19,43,610 should parse as 1943610
        assert any(n.value == Decimal("1943610") for n in nums)


class TestTruthSet:
    def test_walks_nested_dict(self):
        truth = collect_truth_set(
            {
                "ticker": "RELIANCE",
                "price": "1436.10",
                "sources": [
                    {"name": "yfinance", "price": "1436.20"},
                    {"name": "moneycontrol", "price": "1436.20"},
                ],
                "spread_pct": "0.0488",
            }
        )
        # Key values present
        assert Decimal("1436.10") in truth
        assert Decimal("1436.20") in truth
        assert Decimal("0.0488") in truth


class TestVerifyClaims:
    def _truth(self):
        return {Decimal("1436.10"), Decimal("1436.20"), Decimal("24.07")}

    def test_quoted_price_passes_within_tolerance(self):
        # User says "1436.1" — 1436.10 is in truth, exact match
        m = verify_claims("Reliance is at ₹1436.1 today.", self._truth())
        assert m == []

    def test_invented_number_flagged(self):
        m = verify_claims("Reliance hit ₹1500 today.", self._truth())
        assert any(x.value == "1500" for x in m)

    def test_nearby_match_within_pct_tolerance(self):
        # 1436.5 vs 1436.10 — diff ~0.028% <= 0.5%
        m = verify_claims("Reliance is around ₹1436.5.", self._truth())
        assert m == []

    def test_small_numbers_ignored(self):
        # "3 sources" shouldn't be flagged just because 3 isn't in truth
        m = verify_claims("Confirmed across 3 sources.", self._truth())
        assert m == []


# ---------------------------------------------------------------------------
# Layer 3 — disclaimer injector
# ---------------------------------------------------------------------------

class _FakeStock:
    __slots__ = ("ticker", "name", "active")

    def __init__(self, t: str, n: str) -> None:
        self.ticker = t
        self.name = n
        self.active = True


@pytest.fixture
def reliance_index():
    return _build_index([_FakeStock("RELIANCE", "Reliance Industries Ltd")])


class TestDisclaimerInjector:
    def test_appends_when_ticker_present(self, reliance_index):
        text = "Reliance is at ₹1436."
        new, injected = maybe_inject_disclaimer(text, reliance_index)
        assert injected is True
        assert INLINE_DISCLAIMER in new

    def test_no_op_when_no_ticker(self, reliance_index):
        text = "P/E is a valuation ratio."
        new, injected = maybe_inject_disclaimer(text, reliance_index)
        assert injected is False
        assert new == text

    def test_idempotent(self, reliance_index):
        text = f"Reliance is at ₹1436.\n\n_{INLINE_DISCLAIMER}_"
        new, injected = maybe_inject_disclaimer(text, reliance_index)
        assert injected is False
        assert new == text


# ---------------------------------------------------------------------------
# Top-level apply_guardrails
# ---------------------------------------------------------------------------

class TestApplyGuardrails:
    def test_blocklist_hit_overrides_in_strict_mode(self, reliance_index):
        text = "Reliance is great. You should buy Reliance now."
        out = apply_guardrails(
            text,
            tool_results={"price": "1436"},
            ticker_index=reliance_index,
            mode="strict",
        )
        assert out.overridden is True
        assert "investment-advice territory" in out.final_text or "factual information" in out.final_text
        assert out.blocklist_hits  # at least one rule matched

    def test_blocklist_hit_does_not_override_in_warn_mode(self, reliance_index):
        """Phase-2 internal-tool default: blocklist hits stay in the audit
        trail but the streamed text is preserved and the disclaimer still
        gets injected."""
        text = "Reliance is great. You should buy Reliance now."
        out = apply_guardrails(
            text,
            tool_results={"price": "1436"},
            ticker_index=reliance_index,
            mode="warn",
        )
        assert out.overridden is False
        # original analyst text is preserved (with disclaimer appended)
        assert "should buy" in out.final_text.lower()
        # but the audit trail records the rule hit
        assert out.blocklist_hits and out.blocklist_hits[0].rule_id == "rec_buy"
        assert out.disclaimer_injected is True

    def test_warn_mode_is_default(self, reliance_index):
        text = "Should I buy Reliance?"
        out = apply_guardrails(
            text,
            tool_results={"price": "1436"},
            ticker_index=reliance_index,
        )
        # With no mode= argument we default to "warn".
        assert out.overridden is False
        assert out.blocklist_hits  # still recorded for audit

    def test_clean_factual_passes_with_disclaimer(self, reliance_index):
        text = "Reliance is at ₹1436.10 with HIGH confidence across 4 sources."
        out = apply_guardrails(
            text,
            tool_results={
                "ticker": "RELIANCE",
                "price": "1436.10",
                "sources": [{"price": "1436.10"}],
            },
            ticker_index=reliance_index,
        )
        assert out.overridden is False
        assert out.disclaimer_injected is True
        assert INLINE_DISCLAIMER in out.final_text

    def test_education_no_ticker_no_disclaimer(self, reliance_index):
        text = "P/E ratio is price divided by earnings per share."
        out = apply_guardrails(
            text,
            tool_results=None,
            ticker_index=reliance_index,
        )
        assert out.overridden is False
        assert out.disclaimer_injected is False
        assert out.final_text == text

    def test_unverified_number_doesnt_block(self, reliance_index):
        # The model invents ₹1500 — not in truth set — should be flagged but
        # NOT cause an override (avoids false-positive UX).
        text = "Reliance at ₹1500."
        out = apply_guardrails(
            text,
            tool_results={"price": "1436.10"},
            ticker_index=reliance_index,
        )
        assert out.overridden is False
        assert out.claim_mismatches  # mismatch reported
        assert any(m.value == "1500" for m in out.claim_mismatches)
