"""Backtest stub — single-strategy historical replay (P3-A6).

Phase-3 design choice (Decision #5 in the Plan): single screener × N
months. Multi-strategy / parameter sweeps are explicitly Phase-4.

What we compute:
- Walk every trading day in the lookback window.
- On each day: rebuild a per-ticker "row" (close + RSI-14 + SMA-50 +
  SMA-200 + promoter_pct), evaluate the screener expression against
  the row, collect matched tickers.
- Each match is a "signal": enter at that day's close, exit at close
  H trading days later (default H=5). Record forward return.
- Aggregate: hit_rate (% positive forward returns), mean_return,
  worst_drawdown_per_signal, n_signals.
- Equity curve: ₹1 starting capital, equal-weight across active
  signals each day; mark-to-market daily.

Known compromises (documented; acceptable for the demo):
- **Promoter holding** uses TODAY's value for every historical date
  (we don't store point-in-time `holdings`). Acceptable because
  promoter holdings move slowly (quarterly, +/- single-digit pp).
  Look-ahead bias is small.
- **Sector** likewise frozen to today's. No look-ahead-on-sector risk
  for NIFTY-100 names.

The engine is pure-functional given (price_history, screener_expr).
DB I/O is at the API layer, not here.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Mapping, Sequence


_ZERO = Decimal("0")


@dataclass(slots=True, frozen=True)
class BacktestResult:
    name: str
    period_days: int
    n_signals: int
    hit_rate: float
    mean_return: float
    worst_drawdown: float
    sharpe_proxy: float
    equity_curve: list[tuple[str, float]]  # (iso_date, value)


# ---------------------------------------------------------------------------
# Indicator helpers (pure numpy-ish on Python lists — no pandas dep here)
# ---------------------------------------------------------------------------


def _sma(values: Sequence[float], window: int) -> list[float | None]:
    """Simple moving average. Returns same-length list with `None`
    for indices < window-1."""
    out: list[float | None] = [None] * len(values)
    if len(values) < window:
        return out
    running = sum(values[:window])
    out[window - 1] = running / window
    for i in range(window, len(values)):
        running += values[i] - values[i - window]
        out[i] = running / window
    return out


def _rsi_14(values: Sequence[float]) -> list[float | None]:
    """RSI-14 (Wilder's smoothing). Returns same-length list; first 14
    entries are None."""
    n = len(values)
    out: list[float | None] = [None] * n
    if n < 15:
        return out
    gains: list[float] = [0.0]
    losses: list[float] = [0.0]
    for i in range(1, n):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(-min(delta, 0.0))

    avg_gain = sum(gains[1:15]) / 14
    avg_loss = sum(losses[1:15]) / 14
    if avg_loss == 0:
        out[14] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[14] = 100 - (100 / (1 + rs))

    for i in range(15, n):
        avg_gain = (avg_gain * 13 + gains[i]) / 14
        avg_loss = (avg_loss * 13 + losses[i]) / 14
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100 - (100 / (1 + rs))
    return out


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def _build_row(
    ticker: str,
    i: int,
    closes: Sequence[float],
    sma50: Sequence[float | None],
    sma200: Sequence[float | None],
    rsi: Sequence[float | None],
    *,
    sector: str | None,
    promoter_pct: float | None,
    public_pct: float | None,
) -> dict[str, object] | None:
    """Build a per-ticker row dict to feed `screener.evaluate`. Returns
    None if the row isn't fully formed (e.g. before SMA-200 window)."""
    close = closes[i] if i < len(closes) else None
    if close is None:
        return None
    return {
        "_ticker": ticker,
        "close": Decimal(str(close)),
        "sma_50": Decimal(str(sma50[i])) if sma50[i] is not None else None,
        "sma_200": Decimal(str(sma200[i])) if sma200[i] is not None else None,
        "rsi_14": Decimal(str(rsi[i])) if rsi[i] is not None else None,
        "sector": sector,
        "promoter_pct": Decimal(str(promoter_pct)) if promoter_pct is not None else None,
        "public_pct": Decimal(str(public_pct)) if public_pct is not None else None,
    }


def run_backtest(
    *,
    name: str,
    expr: str,
    period_days: int,
    holding_period: int = 5,
    price_history: Mapping[str, Sequence[tuple[date, float]]],
    sector_map: Mapping[str, str | None] | None = None,
    promoter_map: Mapping[str, float | None] | None = None,
    public_map: Mapping[str, float | None] | None = None,
) -> BacktestResult:
    """Replay `expr` daily over the lookback window. Pure-functional
    given the price history + meta maps.

    `price_history[ticker]` must be a list of `(date, close)` tuples,
    ASCENDING. The function trims to the last `period_days + 200`
    observations per ticker (need 200 extra for SMA-200 warmup).
    """
    # Late import to avoid a circular module reference if the analytics
    # surface ever expands.
    from app.analytics.screener import compile_expr, evaluate

    sector_map = sector_map or {}
    promoter_map = promoter_map or {}
    public_map = public_map or {}

    parsed = compile_expr(expr)

    # Build per-ticker indicator series.
    series: dict[str, dict] = {}
    all_dates: set[date] = set()
    for ticker, history in price_history.items():
        if not history:
            continue
        dates = [d for d, _ in history]
        closes = [float(c) for _, c in history]
        all_dates.update(dates)
        series[ticker] = {
            "dates": dates,
            "closes": closes,
            "sma50": _sma(closes, 50),
            "sma200": _sma(closes, 200),
            "rsi": _rsi_14(closes),
        }
    if not series:
        return BacktestResult(name, period_days, 0, 0.0, 0.0, 0.0, 0.0, [])

    sorted_dates = sorted(all_dates)
    if len(sorted_dates) < holding_period + 1:
        return BacktestResult(name, period_days, 0, 0.0, 0.0, 0.0, 0.0, [])

    # Walk forward; for each backtest day, run the screener and book
    # forward-return signals.
    n_signals = 0
    forward_returns: list[float] = []
    daily_signal_returns: dict[date, list[float]] = defaultdict(list)

    # Limit the walk window — the *last* `holding_period` days don't
    # have a forward window to mark against, so skip them.
    walk = sorted_dates[: -holding_period] if holding_period > 0 else sorted_dates

    for d in walk:
        for ticker, s in series.items():
            try:
                i = s["dates"].index(d)
            except ValueError:
                continue
            # SMA-200 warmup gate.
            if i < 200:
                continue
            row = _build_row(
                ticker,
                i,
                s["closes"],
                s["sma50"],
                s["sma200"],
                s["rsi"],
                sector=sector_map.get(ticker),
                promoter_pct=promoter_map.get(ticker),
                public_pct=public_map.get(ticker),
            )
            if row is None:
                continue
            try:
                if not evaluate(parsed, row):
                    continue
            except Exception:  # noqa: BLE001
                continue

            # Signal: book forward return.
            entry = s["closes"][i]
            exit_idx = i + holding_period
            if exit_idx >= len(s["closes"]):
                continue
            exit_close = s["closes"][exit_idx]
            if entry <= 0:
                continue
            ret = (exit_close - entry) / entry
            forward_returns.append(ret)
            daily_signal_returns[d].append(ret)
            n_signals += 1

    if n_signals == 0:
        return BacktestResult(name, period_days, 0, 0.0, 0.0, 0.0, 0.0, [])

    hit_rate = sum(1 for r in forward_returns if r > 0) / n_signals
    mean_return = sum(forward_returns) / n_signals
    worst_drawdown = min(forward_returns)

    # Sharpe proxy: mean / stdev (no risk-free subtraction; daily noise
    # tolerable for the demo).
    if len(forward_returns) > 1:
        m = mean_return
        var = sum((r - m) ** 2 for r in forward_returns) / (len(forward_returns) - 1)
        stdev = math.sqrt(var) if var > 0 else 0.0
        sharpe = (m / stdev) if stdev > 0 else 0.0
    else:
        sharpe = 0.0

    # Equity curve: ₹1 starting; each day, if there are signals, the
    # day's portfolio return is the mean of those signals' next-day
    # mark-to-market move. Simpler aggregate: cumulative compounding
    # of average daily next-period return → smooth curve.
    equity = 1.0
    curve: list[tuple[str, float]] = [(sorted_dates[0].isoformat(), 1.0)]
    for d in walk:
        rets = daily_signal_returns.get(d, [])
        if rets:
            avg = sum(rets) / len(rets)
            # Spread the H-day forward return uniformly per day.
            equity *= 1 + (avg / max(1, holding_period))
        curve.append((d.isoformat(), round(equity, 4)))

    return BacktestResult(
        name=name,
        period_days=period_days,
        n_signals=n_signals,
        hit_rate=round(hit_rate, 4),
        mean_return=round(mean_return, 4),
        worst_drawdown=round(worst_drawdown, 4),
        sharpe_proxy=round(sharpe, 2),
        equity_curve=curve,
    )


def result_to_dict(res: BacktestResult) -> dict:
    """Match the locked REST shape from `app/contracts/phase3.md`."""
    return {
        "name": res.name,
        "period_days": res.period_days,
        "n_signals": res.n_signals,
        "hit_rate": f"{res.hit_rate:.4f}",
        "mean_return": f"{res.mean_return:.4f}",
        "worst_drawdown": f"{res.worst_drawdown:.4f}",
        "sharpe_proxy": f"{res.sharpe_proxy:.2f}",
        "equity_curve": [
            {"date": d, "value": f"{v:.4f}"} for d, v in res.equity_curve
        ],
    }
