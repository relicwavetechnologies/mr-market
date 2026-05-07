"""GET /holding/{ticker} — quarterly NSE shareholding pattern.

Returns the latest N quarters with computed QoQ and YoY deltas on
`promoter_pct`, plus a tiny qualitative summary that the LLM can use
without inventing numbers.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources.nse_shareholding import quarter_label
from app.db.models.holding import Holding
from app.db.session import get_session

router = APIRouter(tags=["holding"])


def _str(d: Decimal | None) -> str | None:
    return str(d) if d is not None else None


def _delta(curr: Decimal | None, prev: Decimal | None) -> Decimal | None:
    if curr is None or prev is None:
        return None
    return (curr - prev).quantize(Decimal("0.0001"))


def _flag_promoter_change(delta: Decimal | None) -> str | None:
    """Tag ≥1pp promoter shifts — these are real signals, not noise."""
    if delta is None:
        return None
    if delta <= Decimal("-1"):
        return "promoter_reduced_significantly"
    if delta >= Decimal("1"):
        return "promoter_increased_significantly"
    return None


@router.get("/holding/{ticker}")
async def holding(
    ticker: str,
    quarters: int = Query(8, ge=1, le=40),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not ticker or len(ticker) > 32:
        raise HTTPException(status_code=400, detail="invalid ticker")
    sym = ticker.upper().strip()

    rows = (
        await session.execute(
            select(Holding)
            .where(Holding.ticker == sym)
            .order_by(desc(Holding.quarter_end))
            .limit(quarters)
        )
    ).scalars().all()
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"no shareholding data for {sym} — has the holdings worker run?",
        )

    # rows are newest-first; build a dict-by-quarter for delta lookups
    by_q: dict[date, Holding] = {r.quarter_end: r for r in rows}

    # Walk back to find the bar from "1 quarter ago" and "4 quarters ago".
    def _shift(q: date, *, qoq: int) -> Holding | None:
        # Indian quarters end Mar/Jun/Sep/Dec. Stepping back 3 months gets the prior quarter.
        month = q.month - (3 * qoq)
        year = q.year
        while month <= 0:
            month += 12
            year -= 1
        target = date(year, month, _last_day(year, month))
        return by_q.get(target)

    series: list[dict[str, Any]] = []
    for r in rows:
        prior = _shift(r.quarter_end, qoq=1)
        yago = _shift(r.quarter_end, qoq=4)
        promoter_qoq = _delta(r.promoter_pct, prior.promoter_pct if prior else None)
        promoter_yoy = _delta(r.promoter_pct, yago.promoter_pct if yago else None)
        public_qoq = _delta(r.public_pct, prior.public_pct if prior else None)
        flag = _flag_promoter_change(promoter_qoq)
        series.append(
            {
                "quarter_end": r.quarter_end.isoformat(),
                "quarter_label": quarter_label(r.quarter_end),
                "promoter_pct": _str(r.promoter_pct),
                "public_pct": _str(r.public_pct),
                "employee_trust_pct": _str(r.employee_trust_pct),
                "promoter_qoq_delta_pp": _str(promoter_qoq),
                "promoter_yoy_delta_pp": _str(promoter_yoy),
                "public_qoq_delta_pp": _str(public_qoq),
                "flag": flag,
                "xbrl_url": r.xbrl_url,
                "submission_date": (
                    r.submission_date.isoformat() if r.submission_date else None
                ),
            }
        )

    latest = rows[0]
    summary: dict[str, Any] = {
        "available": True,
        "latest_quarter": latest.quarter_end.isoformat(),
        "latest_quarter_label": quarter_label(latest.quarter_end),
        "promoter_pct": _str(latest.promoter_pct),
        "public_pct": _str(latest.public_pct),
        "promoter_qoq_delta_pp": series[0]["promoter_qoq_delta_pp"],
        "promoter_yoy_delta_pp": series[0]["promoter_yoy_delta_pp"],
        "flag": series[0]["flag"],
    }

    return {
        "ticker": sym,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "series": series,
    }


def _last_day(year: int, month: int) -> int:
    """Calendar last-day-of-month — we only call this for Mar/Jun/Sep/Dec."""
    return {3: 31, 6: 30, 9: 30, 12: 31}.get(month, 28)
