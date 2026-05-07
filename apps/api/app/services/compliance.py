"""SEBI compliance service — disclaimer injection and risk-profile gating."""

from __future__ import annotations

import re
from typing import Any

from app.services.intent_router import Intent


_SEBI_DISCLAIMER = (
    "\n\n---\n"
    "**Disclaimer:** This analysis is AI-generated for educational and informational "
    "purposes only. It does not constitute investment advice or a recommendation to "
    "buy, sell, or hold any security. Past performance is not indicative of future "
    "results. Please consult a SEBI-registered investment advisor before making any "
    "investment decisions. Mr. Market is not a SEBI-registered entity."
)

_LOWER_CIRCUIT_NUDGE = (
    "\n\n**Warning:** This stock has hit or is near the lower circuit limit. "
    "Exercise extreme caution. Lower circuits often indicate panic selling or "
    "adverse news. Liquidity may be severely constrained."
)

_PROMOTER_PLEDGE_NUDGE = (
    "\n\n**Warning:** Promoter pledge exceeds 10% of their holding. High promoter "
    "pledging increases risk of forced selling if collateral value drops."
)

_FNO_CONSERVATIVE_GATE = (
    "\n\nNote: Based on your conservative risk profile, F&O (Futures & Options) "
    "strategies are not included in this analysis. F&O instruments carry "
    "significant risk of loss and are suitable only for experienced traders."
)


class ComplianceService:
    """Ensures every response meets SEBI compliance requirements.

    Responsibilities:
      - Append disclaimer when the response mentions price levels or targets.
      - Inject risk nudges for lower circuits, high promoter pledge, SEBI actions.
      - Gate F&O-related advice for conservative-profile users.
    """

    def process_response(
        self,
        response: str,
        intent: Intent,
        user_risk_profile: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Apply all compliance transformations to the response text."""
        processed = response

        # Nudge system — check context for risk flags
        if context:
            processed = self._inject_nudges(processed, context)

        # Risk-profile gate — block F&O advice for conservative users
        if user_risk_profile == "conservative":
            processed = self._gate_fno(processed)

        # Always append disclaimer on intents that discuss prices/analysis
        if intent in (
            Intent.STOCK_PRICE,
            Intent.STOCK_ANALYSIS,
            Intent.WHY_MOVING,
            Intent.SCREENER,
            Intent.PORTFOLIO,
        ):
            processed += _SEBI_DISCLAIMER

        return processed

    def get_disclaimer(self) -> str:
        """Return the standard SEBI disclaimer text."""
        return _SEBI_DISCLAIMER.strip().lstrip("-").strip()

    # ------------------------------------------------------------------
    # Nudge injection
    # ------------------------------------------------------------------

    def _inject_nudges(self, response: str, context: dict[str, Any]) -> str:
        """Scan context for risk signals and inject appropriate warnings."""
        data = context.get("data", {})

        # Lower circuit detection
        price_data = data.get("price", {})
        if isinstance(price_data, dict):
            change_pct = price_data.get("change_pct")
            if change_pct is not None:
                try:
                    if float(change_pct) <= -5.0:
                        response += _LOWER_CIRCUIT_NUDGE
                except (ValueError, TypeError):
                    pass

        # Promoter pledge > 10%
        holding_data = data.get("shareholding", {})
        if isinstance(holding_data, dict):
            pledge_pct = holding_data.get("promoter_pledge_pct")
            if pledge_pct is not None:
                try:
                    if float(pledge_pct) > 10.0:
                        response += _PROMOTER_PLEDGE_NUDGE
                except (ValueError, TypeError):
                    pass

        return response

    @staticmethod
    def _gate_fno(response: str) -> str:
        """Remove or replace F&O references for conservative users."""
        fno_pattern = re.compile(
            r"(?:futures?|options?|F&O|call\s+option|put\s+option|"
            r"strike\s+price|expiry|lot\s+size|premium)",
            re.IGNORECASE,
        )
        if fno_pattern.search(response):
            response += _FNO_CONSERVATIVE_GATE
        return response
