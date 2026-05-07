"""Fundamental scoring engine — evaluates a stock's financial health."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScoreComponent:
    """Individual score for one fundamental metric."""
    metric: str
    value: float | None
    score: int  # 0-10
    comment: str


@dataclass
class FundamentalScorecard:
    """Aggregated fundamental score for a stock."""
    ticker: str
    total_score: int  # 0-100
    grade: str  # A, B, C, D, F
    components: list[ScoreComponent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "total_score": self.total_score,
            "grade": self.grade,
            "components": [
                {
                    "metric": c.metric,
                    "value": c.value,
                    "score": c.score,
                    "comment": c.comment,
                }
                for c in self.components
            ],
        }


class FundamentalScorer:
    """Compute a scorecard from raw fundamental data.

    Evaluates:
      - P/E vs industry average
      - Debt-to-Equity ratio health
      - ROE / ROCE quality
      - Revenue and profit growth trajectory
      - Dividend yield attractiveness
    """

    def score(self, ticker: str, data: dict[str, Any]) -> FundamentalScorecard:
        """Generate a scorecard from a fundamentals data dict."""
        components: list[ScoreComponent] = []

        components.append(self._score_pe(data))
        components.append(self._score_debt_equity(data))
        components.append(self._score_roe(data))
        components.append(self._score_roce(data))
        components.append(self._score_revenue_growth(data))
        components.append(self._score_profit_growth(data))
        components.append(self._score_dividend_yield(data))

        valid_scores = [c.score for c in components if c.value is not None]
        if valid_scores:
            # Scale to 0-100
            max_possible = len(valid_scores) * 10
            total = round(sum(valid_scores) / max_possible * 100)
        else:
            total = 0

        grade = self._total_to_grade(total)

        return FundamentalScorecard(
            ticker=ticker,
            total_score=total,
            grade=grade,
            components=components,
        )

    # ------------------------------------------------------------------
    # Individual metric scorers (each returns 0-10)
    # ------------------------------------------------------------------

    @staticmethod
    def _score_pe(data: dict[str, Any]) -> ScoreComponent:
        """P/E relative to industry."""
        pe = data.get("pe")
        pe_industry = data.get("pe_industry")

        if pe is None:
            return ScoreComponent("P/E Ratio", None, 0, "Data not available")

        pe_val = float(pe)

        if pe_industry is not None:
            industry_val = float(pe_industry)
            if industry_val > 0:
                ratio = pe_val / industry_val
                if ratio < 0.7:
                    return ScoreComponent("P/E Ratio", pe_val, 9, "Significantly below industry P/E — potentially undervalued")
                if ratio < 1.0:
                    return ScoreComponent("P/E Ratio", pe_val, 7, "Below industry P/E — reasonably valued")
                if ratio < 1.3:
                    return ScoreComponent("P/E Ratio", pe_val, 5, "Near industry P/E — fairly valued")
                return ScoreComponent("P/E Ratio", pe_val, 3, "Above industry P/E — potentially overvalued")

        if pe_val < 15:
            return ScoreComponent("P/E Ratio", pe_val, 8, "Low P/E — value territory")
        if pe_val < 25:
            return ScoreComponent("P/E Ratio", pe_val, 6, "Moderate P/E")
        if pe_val < 40:
            return ScoreComponent("P/E Ratio", pe_val, 4, "High P/E — growth priced in")
        return ScoreComponent("P/E Ratio", pe_val, 2, "Very high P/E — expensive")

    @staticmethod
    def _score_debt_equity(data: dict[str, Any]) -> ScoreComponent:
        """Debt-to-Equity health."""
        de = data.get("debt_equity")
        if de is None:
            return ScoreComponent("D/E Ratio", None, 0, "Data not available")

        de_val = float(de)
        if de_val < 0.1:
            return ScoreComponent("D/E Ratio", de_val, 10, "Virtually debt-free")
        if de_val < 0.5:
            return ScoreComponent("D/E Ratio", de_val, 8, "Low debt — healthy balance sheet")
        if de_val < 1.0:
            return ScoreComponent("D/E Ratio", de_val, 6, "Moderate debt levels")
        if de_val < 2.0:
            return ScoreComponent("D/E Ratio", de_val, 4, "High debt — monitor closely")
        return ScoreComponent("D/E Ratio", de_val, 2, "Very high leverage — risky")

    @staticmethod
    def _score_roe(data: dict[str, Any]) -> ScoreComponent:
        """Return on Equity quality."""
        roe = data.get("roe")
        if roe is None:
            return ScoreComponent("ROE", None, 0, "Data not available")

        roe_val = float(roe)
        if roe_val > 25:
            return ScoreComponent("ROE", roe_val, 10, "Excellent return on equity")
        if roe_val > 15:
            return ScoreComponent("ROE", roe_val, 7, "Good return on equity")
        if roe_val > 10:
            return ScoreComponent("ROE", roe_val, 5, "Average return on equity")
        if roe_val > 0:
            return ScoreComponent("ROE", roe_val, 3, "Below-average return on equity")
        return ScoreComponent("ROE", roe_val, 1, "Negative ROE — equity eroding")

    @staticmethod
    def _score_roce(data: dict[str, Any]) -> ScoreComponent:
        """Return on Capital Employed quality."""
        roce = data.get("roce")
        if roce is None:
            return ScoreComponent("ROCE", None, 0, "Data not available")

        roce_val = float(roce)
        if roce_val > 25:
            return ScoreComponent("ROCE", roce_val, 10, "Excellent capital efficiency")
        if roce_val > 15:
            return ScoreComponent("ROCE", roce_val, 7, "Good capital efficiency")
        if roce_val > 10:
            return ScoreComponent("ROCE", roce_val, 5, "Average capital efficiency")
        if roce_val > 0:
            return ScoreComponent("ROCE", roce_val, 3, "Poor capital efficiency")
        return ScoreComponent("ROCE", roce_val, 1, "Negative ROCE — destroying value")

    @staticmethod
    def _score_revenue_growth(data: dict[str, Any]) -> ScoreComponent:
        """Revenue growth trajectory."""
        growth = data.get("revenue_growth_pct")
        if growth is None:
            return ScoreComponent("Revenue Growth", None, 0, "Data not available")

        g = float(growth)
        if g > 20:
            return ScoreComponent("Revenue Growth", g, 9, "Strong revenue growth")
        if g > 10:
            return ScoreComponent("Revenue Growth", g, 7, "Healthy revenue growth")
        if g > 0:
            return ScoreComponent("Revenue Growth", g, 5, "Modest positive growth")
        if g > -10:
            return ScoreComponent("Revenue Growth", g, 3, "Revenue declining")
        return ScoreComponent("Revenue Growth", g, 1, "Significant revenue decline")

    @staticmethod
    def _score_profit_growth(data: dict[str, Any]) -> ScoreComponent:
        """Profit growth trajectory."""
        growth = data.get("profit_growth_pct")
        if growth is None:
            return ScoreComponent("Profit Growth", None, 0, "Data not available")

        g = float(growth)
        if g > 25:
            return ScoreComponent("Profit Growth", g, 9, "Strong profit growth")
        if g > 10:
            return ScoreComponent("Profit Growth", g, 7, "Healthy profit growth")
        if g > 0:
            return ScoreComponent("Profit Growth", g, 5, "Modest positive growth")
        if g > -15:
            return ScoreComponent("Profit Growth", g, 3, "Profits declining")
        return ScoreComponent("Profit Growth", g, 1, "Severe profit decline")

    @staticmethod
    def _score_dividend_yield(data: dict[str, Any]) -> ScoreComponent:
        """Dividend yield attractiveness."""
        dy = data.get("dividend_yield_pct")
        if dy is None:
            return ScoreComponent("Dividend Yield", None, 0, "Data not available")

        dy_val = float(dy)
        if dy_val > 4:
            return ScoreComponent("Dividend Yield", dy_val, 9, "High dividend yield")
        if dy_val > 2:
            return ScoreComponent("Dividend Yield", dy_val, 7, "Moderate dividend yield")
        if dy_val > 0.5:
            return ScoreComponent("Dividend Yield", dy_val, 5, "Low but positive dividend")
        if dy_val > 0:
            return ScoreComponent("Dividend Yield", dy_val, 3, "Token dividend")
        return ScoreComponent("Dividend Yield", dy_val, 2, "No dividend")

    @staticmethod
    def _total_to_grade(total: int) -> str:
        """Map a 0-100 score to a letter grade."""
        if total >= 80:
            return "A"
        if total >= 65:
            return "B"
        if total >= 50:
            return "C"
        if total >= 35:
            return "D"
        return "F"
