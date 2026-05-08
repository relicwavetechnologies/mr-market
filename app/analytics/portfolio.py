"""Portfolio diagnostics (P3-A5).

Pure-functional analytics over a list of `(ticker, quantity, avg_price)`
positions. Returns a JSON-serialisable diagnostics dict matching the
shape locked in `app/contracts/phase3.md::GET /portfolio/{id}/diagnostics`.

What we compute:
- **Mark-to-market value** per position from the latest cross-validated
  quote (yfinance / NSE / Screener / Moneycontrol) — same source the
  chat surface uses, so numbers tie out across the demo.
- **Concentration** — top-5 % of total value + Herfindahl-Hirschman
  Index over position weights (0..1; higher = more concentrated).
- **Sector mix** — % of portfolio value per sector.
- **Beta blend** — value-weighted yfinance beta. Falls back to 1.0 for
  positions with missing beta (and we surface the missing-beta count
  separately so the LLM can disclaim if the blend is shaky).
- **Dividend yield** — value-weighted yfinance dividend yield.
- **Drawdown 1y** — peak-to-trough drawdown of a synthetic value series
  built by mark-to-marketing each position daily over the last year
  (using `prices_daily.close`). One-year window because that's the
  Phase-3 demo horizon; full-period drawdown is Phase 4.

Pure-functional: the public `compute_diagnostics()` takes the position
list, the live quote map, the sector map, and the price-history map.
The DB-side wiring + quote fan-out lives at the API layer, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping


_ZERO = Decimal("0")
_ONE = Decimal("1")


@dataclass(slots=True, frozen=True)
class Position:
    """One holding with its current valuation."""

    ticker: str
    quantity: int
    avg_price: Decimal | None
    current_price: Decimal | None  # None when the live quote failed

    @property
    def market_value(self) -> Decimal:
        if self.current_price is None:
            return _ZERO
        return self.current_price * Decimal(self.quantity)


def _quantize(d: Decimal | float | int, places: int = 2) -> str:
    """Stringify with fixed precision — matches the wire convention used
    everywhere else in the contract (Decimals → strings)."""
    if isinstance(d, (int, float)):
        d = Decimal(str(d))
    q = Decimal("1").scaleb(-places)
    try:
        return str(d.quantize(q))
    except Exception:  # noqa: BLE001
        return str(d)


def _safe_div(num: Decimal, den: Decimal) -> Decimal:
    return (num / den) if den > _ZERO else _ZERO


def _herfindahl(weights: list[Decimal]) -> Decimal:
    """HHI = Σ w_i² where w_i ∈ [0,1]. 1.0 = single-name; 1/N = uniform."""
    return sum((w * w for w in weights), start=_ZERO)


def _top_n_pct(weights: list[Decimal], n: int) -> Decimal:
    if not weights:
        return _ZERO
    return sum(sorted(weights, reverse=True)[:n], start=_ZERO) * Decimal(100)


def _sector_breakdown(
    positions: list[Position],
    sector_map: Mapping[str, str | None],
    total_value: Decimal,
) -> list[dict[str, str]]:
    """Aggregate position values by sector. Returns sorted (desc by pct)
    list of `{sector, pct}`. Tickers without a sector roll into "Other"."""
    if total_value <= _ZERO:
        return []
    buckets: dict[str, Decimal] = {}
    for p in positions:
        sec = sector_map.get(p.ticker) or "Other"
        buckets[sec] = buckets.get(sec, _ZERO) + p.market_value

    out: list[dict[str, str]] = []
    for sec, val in sorted(buckets.items(), key=lambda kv: kv[1], reverse=True):
        pct = _safe_div(val, total_value) * Decimal(100)
        out.append({"sector": sec, "pct": _quantize(pct, 1)})
    return out


def _value_weighted(
    positions: list[Position],
    factor_map: Mapping[str, Decimal | None],
    total_value: Decimal,
    *,
    fallback: Decimal,
) -> tuple[Decimal, int]:
    """Value-weighted average of a factor across positions; positions
    with missing factor values fall back to `fallback`. Returns
    (weighted, n_missing)."""
    if total_value <= _ZERO:
        return _ZERO, 0
    weighted = _ZERO
    n_missing = 0
    for p in positions:
        v = factor_map.get(p.ticker)
        if v is None:
            v = fallback
            n_missing += 1
        weight = _safe_div(p.market_value, total_value)
        weighted += weight * v
    return weighted, n_missing


def _drawdown_1y(
    positions: list[Position],
    price_history: Mapping[str, list[tuple[str, Decimal]]],
) -> Decimal:
    """Peak-to-trough drawdown over the last year of a synthetic
    portfolio value series.

    `price_history[ticker]` is a list of `(iso_date, close)` ascending.
    Returns the max drawdown as a decimal (negative, e.g. -0.074 = -7.4%).
    Returns 0 if we don't have enough history to compute it."""
    if not positions or not price_history:
        return _ZERO

    # Union of all dates across positions, ordered.
    all_dates: set[str] = set()
    for p in positions:
        for d, _ in price_history.get(p.ticker, []):
            all_dates.add(d)
    if len(all_dates) < 30:
        return _ZERO  # not enough series to be meaningful
    dates = sorted(all_dates)

    # Index price-by-ticker by date for forward-fill semantics.
    pbm: dict[str, dict[str, Decimal]] = {
        p.ticker: dict(price_history.get(p.ticker, [])) for p in positions
    }

    # Walk dates; mark-to-market the portfolio. Forward-fill missing
    # closes per ticker (markets shut on a given day for that name).
    last_close: dict[str, Decimal] = {p.ticker: _ZERO for p in positions}
    series: list[Decimal] = []
    for d in dates:
        for p in positions:
            close = pbm[p.ticker].get(d)
            if close is not None:
                last_close[p.ticker] = close
        value = sum(
            (last_close[p.ticker] * Decimal(p.quantity) for p in positions),
            start=_ZERO,
        )
        series.append(value)

    # Strip leading zeros (positions with no history yet).
    while series and series[0] == _ZERO:
        series.pop(0)
    if len(series) < 2:
        return _ZERO

    peak = series[0]
    max_dd = _ZERO
    for v in series:
        if v > peak:
            peak = v
        if peak > _ZERO:
            dd = (v - peak) / peak  # ≤ 0
            if dd < max_dd:
                max_dd = dd
    return max_dd


def compute_diagnostics(
    positions: list[Position],
    *,
    sector_map: Mapping[str, str | None],
    beta_map: Mapping[str, Decimal | None],
    div_yield_map: Mapping[str, Decimal | None],
    price_history: Mapping[str, list[tuple[str, Decimal]]],
) -> dict:
    """Pure-functional diagnostics over a fully-resolved position list.

    All inputs are plain dicts so the function is trivial to unit-test:
    no DB session, no scrape, no async.
    """
    total_value = sum((p.market_value for p in positions), start=_ZERO)
    weights = [
        _safe_div(p.market_value, total_value) for p in positions if total_value > _ZERO
    ]

    # Concentration.
    top_5_pct = _top_n_pct(weights, 5)
    hhi = _herfindahl(weights)

    # Sector breakdown.
    sector_pct = _sector_breakdown(positions, sector_map, total_value)

    # Beta blend (default 1.0 for missing).
    beta, n_missing_beta = _value_weighted(
        positions, beta_map, total_value, fallback=_ONE
    )

    # Dividend yield (default 0.0 for missing).
    div_yield, _ = _value_weighted(
        positions, div_yield_map, total_value, fallback=_ZERO
    )

    drawdown = _drawdown_1y(positions, price_history)

    return {
        "n_positions": len(positions),
        "total_value_inr": _quantize(total_value, 2),
        "concentration": {
            "top_5_pct": _quantize(top_5_pct, 1),
            "herfindahl": _quantize(hhi, 4),
        },
        "sector_pct": sector_pct,
        "beta_blend": _quantize(beta, 2),
        "div_yield": _quantize(div_yield * Decimal(100), 2),  # as %
        "drawdown_1y": _quantize(drawdown * Decimal(100), 1),  # as %
        "diagnostics_notes": {
            "missing_beta_count": n_missing_beta,
            "n_priced": sum(1 for p in positions if p.current_price is not None),
        },
    }
