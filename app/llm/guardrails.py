"""SEBI safe-harbour guardrails — applied AFTER the LLM finishes.

Three layers, in order:

  1. **Blocklist regex** on the assistant's text. Catches anything the system
     prompt + intent router missed: imperative buy/sell verbs, price targets,
     stop-loss / entry levels, F&O strategy talk, personalisation. If any
     pattern fires we override the message with a canonical refusal.

  2. **Numeric claim verifier**. Extract every number/percentage/currency
     amount from the assistant's text and try to match each against the
     tool-call result JSON (with tolerance). Unmatched numbers don't BLOCK
     the response (too easy to misfire on derived values like change %); we
     just record them in `chat_audit.flagged` so we can audit them later.

  3. **Ticker → disclaimer injector**. If any NIFTY-50 ticker appears in the
     final assistant text, append the inline factual-information disclaimer
     once. Idempotent.

The orchestrator buffers the streamed text, runs `apply_guardrails(...)` once
at `done`, and if `override_message` is set, the frontend swaps the displayed
message for the override + shows a "⚠️ replaced for compliance" banner.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.analytics.ticker_ner import TickerIndex
from app.llm.prompts import INLINE_DISCLAIMER

# ---------------------------------------------------------------------------
# Layer 1 — blocklist
# ---------------------------------------------------------------------------

# Each rule has a stable `id` we can log + a category for the frontend banner.
# Patterns are case-insensitive, anchored to word boundaries so we don't catch
# "buyout" when matching "buy".
BLOCKLIST: list[tuple[str, str, re.Pattern[str]]] = [
    # --- imperative recommendation verbs ----
    # Catches "should I buy X", "should you sell", "must we exit", "I recommend
    # buying", "we advise selling", etc. The bridge "(?:\w+\s+){0,3}" allows
    # an optional pronoun / subject between the modal and the verb.
    (
        "rec_buy",
        "recommendation",
        re.compile(
            r"\b(?:should|must|recommend|recommending|advise|advising|suggest|suggesting)"
            r"\s+(?:\w+\s+){0,3}"
            r"(?:buy|buying|sell|selling|exit|exiting|short|shorting|"
            r"accumulate|accumulating|trim|trimming)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "rec_buy_at",
        "recommendation",
        re.compile(r"\b(?:buy|sell|enter|exit)\s+(?:at|near|around)\s+₹?\s*\d", re.IGNORECASE),
    ),
    (
        "rec_book_profit",
        "recommendation",
        re.compile(r"\bbook\s+(?:your\s+)?profit\b", re.IGNORECASE),
    ),
    (
        "rec_load_up",
        "recommendation",
        re.compile(r"\b(?:load\s+up|stock\s+up|pile\s+in)\b", re.IGNORECASE),
    ),
    (
        "rec_sip_this",
        "recommendation",
        re.compile(r"\bSIP\s+(?:this|in|into)\b", re.IGNORECASE),
    ),
    # --- targets ----------------------------------------------------------
    (
        "tgt_price",
        "target",
        re.compile(
            r"\b(?:price\s+)?target(?:s)?\s+(?:of\s+|at\s+|is\s+|:?\s*)?₹?\s*\d",
            re.IGNORECASE,
        ),
    ),
    (
        "tgt_fair_value",
        "target",
        re.compile(r"\bfair\s+value\s+(?:of\s+|is\s+|:?\s*)?₹?\s*\d", re.IGNORECASE),
    ),
    (
        "tgt_upside",
        "target",
        re.compile(r"\b\d+\s*%\s+upside\b", re.IGNORECASE),
    ),
    # --- stop-loss / entry / SL ------------------------------------------
    (
        "sl_at",
        "stop_loss",
        re.compile(r"\bstop[\s-]?loss\s+(?:at|of|near)\b", re.IGNORECASE),
    ),
    (
        "sl_short",
        "stop_loss",
        re.compile(r"\bSL\s+(?:at|of|near)\s+₹?\s*\d", re.IGNORECASE),
    ),
    (
        "entry_at",
        "entry",
        re.compile(r"\bentry\s+(?:at|near|around|level)\s+₹?\s*\d", re.IGNORECASE),
    ),
    # --- F&O / derivatives strategy --------------------------------------
    (
        "fno_options_strategy",
        "fno",
        re.compile(
            r"\b(?:call|put)\s+(?:option|spread|strategy)\b|"
            r"\b(?:bull|bear)\s+(?:call|put)\s+spread\b|"
            r"\biron\s+condor\b|\bstraddle\b|\bstrangle\b",
            re.IGNORECASE,
        ),
    ),
    (
        "fno_intraday",
        "intraday",
        re.compile(r"\bintraday\s+(?:call|trade|setup|long|short|buy|sell)\b", re.IGNORECASE),
    ),
    # --- personalised advice -----------------------------------------------
    (
        "pers_your_portfolio",
        "personalised",
        re.compile(r"\bfor\s+your\s+portfolio\b", re.IGNORECASE),
    ),
    (
        "pers_you_should_invest",
        "personalised",
        re.compile(r"\byou\s+should\s+(?:invest|put\s+money)\b", re.IGNORECASE),
    ),
]


@dataclass(slots=True, frozen=True)
class BlocklistHit:
    rule_id: str
    category: str
    matched_text: str


def find_blocklist_hits(text: str) -> list[BlocklistHit]:
    """Return every blocklist match found in ``text``."""
    if not text:
        return []
    out: list[BlocklistHit] = []
    for rule_id, category, pattern in BLOCKLIST:
        for m in pattern.finditer(text):
            out.append(
                BlocklistHit(
                    rule_id=rule_id,
                    category=category,
                    matched_text=m.group(0)[:80],
                )
            )
    return out


# ---------------------------------------------------------------------------
# Layer 2 — numeric claim verifier
# ---------------------------------------------------------------------------

# Match Indian-style and Western-style numbers, with optional ₹/%/cr/lakh suffix.
_NUMBER_RE = re.compile(
    r"(?P<value>[-+]?\d+(?:[,\s]\d+)*(?:\.\d+)?)"
    r"(?:\s*(?P<unit>%|lakh|crore|cr|bn|million|mn|thousand|k|b))?",
    re.IGNORECASE,
)


@dataclass(slots=True, frozen=True)
class ExtractedNumber:
    raw: str
    value: Decimal
    unit: str | None


def _to_decimal(raw: str) -> Decimal | None:
    cleaned = raw.replace(",", "").replace(" ", "")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def extract_numbers(text: str) -> list[ExtractedNumber]:
    if not text:
        return []
    out: list[ExtractedNumber] = []
    for m in _NUMBER_RE.finditer(text):
        v = _to_decimal(m.group("value"))
        if v is None:
            continue
        unit = (m.group("unit") or "").lower() or None
        out.append(ExtractedNumber(raw=m.group(0), value=v, unit=unit))
    return out


def collect_truth_set(tool_results: dict[str, Any] | list[Any] | None) -> set[Decimal]:
    """Walk the tool-result payload and gather every number we find as Decimals.

    Idea: any number the LLM quotes in its answer should be derivable from
    something a tool produced. Walking the JSON tree once gives us a fast
    membership test.
    """
    found: set[Decimal] = set()

    def _walk(v: Any) -> None:
        if isinstance(v, dict):
            for vv in v.values():
                _walk(vv)
        elif isinstance(v, list):
            for vv in v:
                _walk(vv)
        elif isinstance(v, (int, float, Decimal)):
            try:
                found.add(Decimal(str(v)))
            except InvalidOperation:
                pass
        elif isinstance(v, str):
            # Many of our payloads pre-stringify Decimals (e.g. "1436.10").
            d = _to_decimal(v)
            if d is not None:
                found.add(d)

    _walk(tool_results)
    return found


@dataclass(slots=True, frozen=True)
class ClaimMismatch:
    raw: str
    value: str            # stringified Decimal
    unit: str | None
    closest: str | None   # stringified Decimal of the nearest truth value
    delta_pct: str | None


def verify_claims(
    text: str,
    truth: set[Decimal],
    *,
    pct_tolerance: float = 0.5,         # ±0.5 %
    abs_tolerance: float = 0.05,        # ±0.05 absolute (for sub-100 currency rounding)
    ignore_below: float = 10.0,         # skip small standalone integers like "3 sources"
) -> list[ClaimMismatch]:
    """Return numbers in ``text`` that don't match any value in the truth set.

    Tolerance is a logical OR: a claim passes if EITHER its absolute distance
    is within ``abs_tolerance`` OR its relative distance is within
    ``pct_tolerance`` of any truth value.
    """
    extracted = extract_numbers(text)
    if not extracted or not truth:
        return [
            ClaimMismatch(raw=e.raw, value=str(e.value), unit=e.unit, closest=None, delta_pct=None)
            for e in extracted
            if abs(e.value) >= Decimal(str(ignore_below))
        ]

    truth_sorted = sorted(truth)
    mismatches: list[ClaimMismatch] = []

    for e in extracted:
        if abs(e.value) < Decimal(str(ignore_below)):
            continue

        # Find the truth value closest in magnitude.
        closest = min(truth_sorted, key=lambda t: abs(t - e.value))
        diff = abs(closest - e.value)
        ref = max(abs(closest), Decimal("1"))
        rel = (diff / ref) * Decimal(100)

        if diff <= Decimal(str(abs_tolerance)) or rel <= Decimal(str(pct_tolerance)):
            continue  # passed

        mismatches.append(
            ClaimMismatch(
                raw=e.raw,
                value=str(e.value),
                unit=e.unit,
                closest=str(closest),
                delta_pct=f"{rel:.4f}",
            )
        )
    return mismatches


# ---------------------------------------------------------------------------
# Layer 3 — ticker → disclaimer injector
# ---------------------------------------------------------------------------


def maybe_inject_disclaimer(text: str, ticker_index: TickerIndex | None) -> tuple[str, bool]:
    """If the answer mentions any covered ticker, append the inline disclaimer.

    Returns ``(new_text, injected)``. Idempotent: if the disclaimer is
    already present (substring match), we don't add a second copy.
    """
    if not text or ticker_index is None:
        return text, False
    if INLINE_DISCLAIMER in text:
        return text, False
    tickers = ticker_index.find_tickers(text)
    if not tickers:
        return text, False
    return text.rstrip() + f"\n\n_{INLINE_DISCLAIMER}_", True


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


REFUSAL_OVERRIDE_TEMPLATE = (
    "I can't share that — what I drafted contained {category} language that "
    "crosses into investment-advice territory ({rule_id}). I can give you "
    "the latest factual price, recent news, or company info instead.\n\n"
    "_This is factual information, not investment advice._"
)


@dataclass(slots=True)
class GuardedOutput:
    final_text: str
    overridden: bool
    blocklist_hits: list[BlocklistHit] = field(default_factory=list)
    claim_mismatches: list[ClaimMismatch] = field(default_factory=list)
    disclaimer_injected: bool = False

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "overridden": self.overridden,
            "disclaimer_injected": self.disclaimer_injected,
            "blocklist_hits": [
                {"rule_id": h.rule_id, "category": h.category, "matched": h.matched_text}
                for h in self.blocklist_hits
            ],
            "claim_mismatches": [
                {
                    "raw": m.raw,
                    "value": m.value,
                    "unit": m.unit,
                    "closest": m.closest,
                    "delta_pct": m.delta_pct,
                }
                for m in self.claim_mismatches
            ],
        }


def apply_guardrails(
    text: str,
    *,
    tool_results: dict[str, Any] | None = None,
    ticker_index: TickerIndex | None = None,
    mode: str = "warn",
) -> GuardedOutput:
    """Run all three layers.

    ``mode``:
      * ``"strict"`` (Phase-1 SEBI mode) — blocklist hits OVERRIDE the text
        with the canonical refusal. Sets ``overridden=True``.
      * ``"warn"`` (Phase-2 internal-tool mode, default) — blocklist hits
        are recorded for the audit trail and the UI banner; the streamed
        text is NOT replaced. The disclaimer injector still runs.

    Claim mismatches are reported in both modes but never trigger an override
    on their own (too easy to misfire on timestamps / dates).
    """
    hits = find_blocklist_hits(text or "")

    if hits and mode == "strict":
        first = hits[0]
        override = REFUSAL_OVERRIDE_TEMPLATE.format(
            category=first.category, rule_id=first.rule_id
        )
        return GuardedOutput(
            final_text=override,
            overridden=True,
            blocklist_hits=hits,
        )

    truth = collect_truth_set(tool_results) if tool_results is not None else set()
    mismatches = verify_claims(text or "", truth) if truth else []

    final_text, injected = maybe_inject_disclaimer(text or "", ticker_index)

    return GuardedOutput(
        final_text=final_text,
        overridden=False,
        blocklist_hits=hits,                 # always recorded
        claim_mismatches=mismatches,
        disclaimer_injected=injected,
    )


# Convenience for tests / debugging.
def _truth_for_log(truth: set[Decimal], limit: int = 30) -> str:
    items = sorted(truth)[:limit]
    return json.dumps([str(x) for x in items])
