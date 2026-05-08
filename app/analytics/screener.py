"""Screener expression engine (P3-A2).

A small, safe DSL for filtering the universe by indicator + holding +
stock-metadata conditions. Pure-Python AST — no SQL injection surface,
no ``eval`` / ``exec``, no attribute access on the row object.

Grammar (case-insensitive on AND/OR/NOT, identifiers are lower-cased)::

    expr        := or_expr
    or_expr     := and_expr ('OR' and_expr)*
    and_expr    := not_expr ('AND' not_expr)*
    not_expr    := 'NOT' not_expr | atom
    atom        := comparison | '(' expr ')'
    comparison  := IDENT op value
    op          := '<' | '<=' | '>' | '>=' | '=' | '==' | '!=' | '<>'
    value       := NUMBER | STRING

Allowed identifiers come from ``ALLOWED_FIELDS`` — anything else fails
fast at parse time with a ``ScreenerError``. NULL handling is consistent
across operators: any comparison against ``None`` returns ``False``,
which means a NULL row never matches and never falsely excludes.

Examples::

    rsi_14 < 30 AND promoter_pct > 50
    sector = 'Financial Services' AND public_pct < 30
    NOT (rsi_14 > 70) AND close > sma_50

Public surface (the only callers should use)::

    compile_expr(expr_str: str) -> Expr           # parse + validate
    evaluate(expr: Expr, row: Mapping) -> bool    # walk against a row
    run_screener(session, expr_str, *, limit, universe?) -> ScreenerResult

The orchestrator-side LLM tool (Dev B) and the REST `/screener/run`
endpoint both call into ``run_screener``.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Stock
from app.db.models.holding import Holding
from app.db.models.technicals import Technicals


# ---------------------------------------------------------------------------
# Field allowlist — the *only* identifiers a user expression may reference.
# Adding a field requires adding it here AND populating it in `_load_rows`.
# ---------------------------------------------------------------------------

# Latest-row fields from the `technicals` table.
_TECHNICALS_FIELDS = {
    "close",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_hist",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "sma_20",
    "sma_50",
    "sma_200",
    "ema_12",
    "ema_26",
    "atr_14",
    "vol_avg_20",
}

# Latest-quarter fields from the `holdings` table.
_HOLDINGS_FIELDS = {
    "promoter_pct",
    "public_pct",
    "employee_trust_pct",
}

# Stock-metadata fields (mostly string).
_STOCKS_FIELDS = {
    "sector",
    "industry",
    "market_cap_inr",
}

ALLOWED_FIELDS: frozenset[str] = frozenset(
    _TECHNICALS_FIELDS | _HOLDINGS_FIELDS | _STOCKS_FIELDS
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ScreenerError(ValueError):
    """All parser / evaluator failures use this error type so callers can
    catch one thing instead of guessing."""


# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FieldRef:
    """RHS reference to another field (e.g. `close > sma_200`). Evaluator
    dereferences against the row at evaluation time."""

    name: str


@dataclass(frozen=True, slots=True)
class Compare:
    field: str
    op: str  # one of: <  <=  >  >=  =  !=
    value: Decimal | str | FieldRef


@dataclass(frozen=True, slots=True)
class And:
    left: "Expr"
    right: "Expr"


@dataclass(frozen=True, slots=True)
class Or:
    left: "Expr"
    right: "Expr"


@dataclass(frozen=True, slots=True)
class Not:
    inner: "Expr"


Expr = Compare | And | Or | Not


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------


_TOKEN_PATTERNS = [
    ("WS", r"\s+"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    # Multi-character operators must come BEFORE the single-character ones.
    ("OP", r"<=|>=|==|!=|<>|<|>|="),
    # Quoted string (single or double) — enclosed text only, no escapes.
    ("STRING", r"'([^']*)'|\"([^\"]*)\""),
    # Number — int or decimal, optional leading minus.
    ("NUMBER", r"-?\d+(?:\.\d+)?"),
    # Identifier — letters / digits / underscore. Boolean keywords handled
    # at a higher layer.
    ("IDENT", r"[A-Za-z_][A-Za-z0-9_]*"),
]
_TOKEN_RE = re.compile(
    "|".join(f"(?P<{name}>{pat})" for name, pat in _TOKEN_PATTERNS)
)


@dataclass(slots=True)
class Token:
    kind: str  # LPAREN | RPAREN | OP | STRING | NUMBER | IDENT
    value: str
    pos: int


def tokenise(s: str) -> list[Token]:
    """Lex an expression string into a stream of tokens. Raises
    ``ScreenerError`` on any unrecognised character — defends against
    SQL-style payloads (`;`, `--`, `*`, etc.) at the very first hop.
    """
    if not s or not s.strip():
        raise ScreenerError("expression is empty")

    tokens: list[Token] = []
    pos = 0
    while pos < len(s):
        m = _TOKEN_RE.match(s, pos)
        if not m:
            raise ScreenerError(
                f"unexpected character at pos {pos}: {s[pos]!r} in {s!r}"
            )
        kind = m.lastgroup
        if kind == "WS":
            pos = m.end()
            continue
        if kind == "STRING":
            # Strip the matching outer quotes — the regex guarantees they
            # exist and match. (Outer-group alternation makes inner-group
            # numbering non-portable, so we slice instead of grouping.)
            raw = m.group(0)
            inner = raw[1:-1]
            tokens.append(Token(kind=kind, value=inner, pos=pos))
        else:
            tokens.append(Token(kind=kind, value=m.group(0), pos=pos))
        pos = m.end()
    return tokens


# ---------------------------------------------------------------------------
# Parser — recursive descent (precedence: NOT > AND > OR)
# ---------------------------------------------------------------------------


_BOOL_KEYWORDS = {"and", "or", "not"}


def _peek(tokens: list[Token], i: int) -> Token | None:
    return tokens[i] if i < len(tokens) else None


def _expect(tokens: list[Token], i: int, kind: str) -> Token:
    tok = _peek(tokens, i)
    if tok is None:
        raise ScreenerError(f"unexpected end of expression — expected {kind}")
    if tok.kind != kind:
        raise ScreenerError(
            f"expected {kind} at pos {tok.pos}, got {tok.kind} {tok.value!r}"
        )
    return tok


def _is_keyword(tok: Token | None, kw: str) -> bool:
    return tok is not None and tok.kind == "IDENT" and tok.value.lower() == kw


def _parse_value(tok: Token) -> Decimal | str | FieldRef:
    if tok.kind == "NUMBER":
        try:
            return Decimal(tok.value)
        except InvalidOperation as e:  # noqa: BLE001
            raise ScreenerError(f"bad number at pos {tok.pos}: {tok.value!r}") from e
    if tok.kind == "STRING":
        return tok.value
    if tok.kind == "IDENT":
        # Field-to-field comparison (e.g. close > sma_200). The RHS field
        # must also be in the allowlist — defends against the user
        # back-dooring an arbitrary attribute through the value position.
        name = tok.value.lower()
        if name in _BOOL_KEYWORDS:
            raise ScreenerError(
                f"unexpected boolean keyword {name!r} at pos {tok.pos}"
            )
        if name not in ALLOWED_FIELDS:
            raise ScreenerError(
                f"unknown field {name!r} on rhs of comparison "
                f"(allowed: {sorted(ALLOWED_FIELDS)})"
            )
        return FieldRef(name=name)
    raise ScreenerError(
        f"expected NUMBER, STRING, or IDENT at pos {tok.pos}, got {tok.kind}"
    )


def _parse_comparison(tokens: list[Token], i: int) -> tuple[Compare, int]:
    field_tok = _peek(tokens, i)
    if field_tok is None or field_tok.kind != "IDENT":
        raise ScreenerError("expected field identifier")
    field = field_tok.value.lower()
    if field in _BOOL_KEYWORDS:
        raise ScreenerError(
            f"unexpected boolean keyword {field!r} at pos {field_tok.pos}"
        )
    if field not in ALLOWED_FIELDS:
        raise ScreenerError(
            f"unknown field {field!r} (allowed: {sorted(ALLOWED_FIELDS)})"
        )
    i += 1

    op_tok = _peek(tokens, i)
    if op_tok is None or op_tok.kind != "OP":
        raise ScreenerError(f"expected operator after {field!r}")
    # Normalise operator spellings.
    op = {"==": "=", "<>": "!="}.get(op_tok.value, op_tok.value)
    i += 1

    val_tok = _peek(tokens, i)
    if val_tok is None:
        raise ScreenerError(f"expected value after {field} {op}")
    value = _parse_value(val_tok)
    i += 1
    return Compare(field=field, op=op, value=value), i


def _parse_atom(tokens: list[Token], i: int) -> tuple[Expr, int]:
    tok = _peek(tokens, i)
    if tok is None:
        raise ScreenerError("unexpected end of expression")
    if tok.kind == "LPAREN":
        node, i = _parse_or(tokens, i + 1)
        _expect(tokens, i, "RPAREN")
        return node, i + 1
    return _parse_comparison(tokens, i)


def _parse_not(tokens: list[Token], i: int) -> tuple[Expr, int]:
    if _is_keyword(_peek(tokens, i), "not"):
        inner, j = _parse_not(tokens, i + 1)
        return Not(inner=inner), j
    return _parse_atom(tokens, i)


def _parse_and(tokens: list[Token], i: int) -> tuple[Expr, int]:
    left, i = _parse_not(tokens, i)
    while _is_keyword(_peek(tokens, i), "and"):
        right, i = _parse_not(tokens, i + 1)
        left = And(left=left, right=right)
    return left, i


def _parse_or(tokens: list[Token], i: int) -> tuple[Expr, int]:
    left, i = _parse_and(tokens, i)
    while _is_keyword(_peek(tokens, i), "or"):
        right, i = _parse_and(tokens, i + 1)
        left = Or(left=left, right=right)
    return left, i


def parse(tokens: list[Token]) -> Expr:
    """Parse a token stream into an Expr tree. Raises ``ScreenerError`` on
    any structural problem (unbalanced parens, missing operator, etc.)."""
    expr, i = _parse_or(tokens, 0)
    if i != len(tokens):
        leftover = tokens[i]
        raise ScreenerError(
            f"unexpected token {leftover.kind} {leftover.value!r} at pos {leftover.pos}"
        )
    return expr


def compile_expr(expr_str: str) -> Expr:
    """One-shot compile from string to validated AST. The cheap public API."""
    return parse(tokenise(expr_str))


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


def _to_decimal(v: Any) -> Decimal | None:
    """Coerce a row value to Decimal for numeric comparison. Returns None
    if v is None or non-numeric (so NULL semantics fall through)."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)):
        try:
            return Decimal(str(v))
        except InvalidOperation:
            return None
    if isinstance(v, str):
        try:
            return Decimal(v)
        except InvalidOperation:
            return None
    return None


def _compare(field_value: Any, op: str, target: Decimal | str) -> bool:
    """Evaluate one comparison. NULL semantics: any compare against None
    returns False. `target` is already a concrete value here — FieldRef
    nodes are dereferenced one layer up in `evaluate`."""
    if field_value is None:
        return False
    if target is None:
        # Dereferenced-from-FieldRef path may produce None for missing rows.
        return False

    if isinstance(target, Decimal):
        lhs = _to_decimal(field_value)
        if lhs is None:
            return False
        if op == "<":
            return lhs < target
        if op == "<=":
            return lhs <= target
        if op == ">":
            return lhs > target
        if op == ">=":
            return lhs >= target
        if op == "=":
            return lhs == target
        if op == "!=":
            return lhs != target
        raise ScreenerError(f"unknown numeric operator: {op}")

    # String comparison — only `=` and `!=` make sense.
    if not isinstance(field_value, str):
        return False
    if op == "=":
        return field_value == target
    if op == "!=":
        return field_value != target
    raise ScreenerError(
        f"string field cannot be compared with {op!r} (use = or !=)"
    )


def evaluate(expr: Expr, row: Mapping[str, Any]) -> bool:
    """Walk an Expr against a single row dict. Returns True if the row
    matches the expression. Pure-functional — never reads anything outside
    `row`. Raises ``ScreenerError`` only on internal bugs (an unknown AST
    node), never on bad data — bad data flows through as False via NULL
    semantics."""
    if isinstance(expr, Compare):
        # Dereference RHS field references — `close > sma_200` becomes
        # `close > <row.sma_200>`. Missing-row → None → False (NULL semantics).
        target = expr.value
        if isinstance(target, FieldRef):
            target = _to_decimal(row.get(target.name))
        return _compare(row.get(expr.field), expr.op, target)
    if isinstance(expr, And):
        return evaluate(expr.left, row) and evaluate(expr.right, row)
    if isinstance(expr, Or):
        return evaluate(expr.left, row) or evaluate(expr.right, row)
    if isinstance(expr, Not):
        return not evaluate(expr.inner, row)
    raise ScreenerError(f"internal error: unknown AST node {type(expr).__name__}")


# ---------------------------------------------------------------------------
# DB-backed runner
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TickerHit:
    symbol: str
    score: float
    hits: dict[str, str]


@dataclass(slots=True)
class ScreenerResult:
    matched: int
    universe_size: int
    exec_ms: int
    tickers: list[TickerHit]


def _row_to_str_dict(field_names: list[str], row: Mapping[str, Any]) -> dict[str, str]:
    """Stringify the relevant row fields for the `hits` payload — matches
    the `tools_call` JSON shape (Decimal → str)."""
    out: dict[str, str] = {}
    for name in field_names:
        v = row.get(name)
        if v is None:
            continue
        out[name] = str(v)
    return out


def _collect_referenced_fields(expr: Expr, into: set[str]) -> None:
    """Walk the AST collecting every field referenced — both Compare.field
    (LHS) and any FieldRef in Compare.value (RHS). Used by the hits
    serialiser so the payload includes every field the expression touched."""
    if isinstance(expr, Compare):
        into.add(expr.field)
        if isinstance(expr.value, FieldRef):
            into.add(expr.value.name)
        return
    if isinstance(expr, (And, Or)):
        _collect_referenced_fields(expr.left, into)
        _collect_referenced_fields(expr.right, into)
        return
    if isinstance(expr, Not):
        _collect_referenced_fields(expr.inner, into)
        return


async def _load_rows(
    session: AsyncSession,
    *,
    universe: list[str] | None,
) -> list[dict[str, Any]]:
    """Build the per-ticker row dicts the evaluator runs against. One row
    per active stock; latest technicals row + latest holdings row joined in.

    Returns dicts keyed on the field names in ``ALLOWED_FIELDS``; absent
    data is omitted (so NULL semantics in `evaluate` apply).
    """
    # Stocks we care about — full active universe by default, or the
    # explicit subset.
    stocks_q = select(Stock).where(Stock.active.is_(True))
    if universe:
        stocks_q = stocks_q.where(Stock.ticker.in_(universe))
    stocks = (await session.execute(stocks_q)).scalars().all()

    if not stocks:
        return []

    tickers = [s.ticker for s in stocks]

    # Latest technicals row per ticker — use a MAX(ts) subquery rather than
    # DISTINCT ON for clarity. NIFTY-100 fits comfortably in memory.
    latest_ts_subq = (
        select(Technicals.ticker, func.max(Technicals.ts).label("max_ts"))
        .where(Technicals.ticker.in_(tickers))
        .group_by(Technicals.ticker)
        .subquery()
    )
    tech_rows = (
        await session.execute(
            select(Technicals)
            .join(
                latest_ts_subq,
                (Technicals.ticker == latest_ts_subq.c.ticker)
                & (Technicals.ts == latest_ts_subq.c.max_ts),
            )
        )
    ).scalars().all()
    tech_by_ticker = {t.ticker: t for t in tech_rows}

    # Latest holdings row per ticker — same shape.
    latest_q_subq = (
        select(Holding.ticker, func.max(Holding.quarter_end).label("max_q"))
        .where(Holding.ticker.in_(tickers))
        .group_by(Holding.ticker)
        .subquery()
    )
    hold_rows = (
        await session.execute(
            select(Holding)
            .join(
                latest_q_subq,
                (Holding.ticker == latest_q_subq.c.ticker)
                & (Holding.quarter_end == latest_q_subq.c.max_q),
            )
        )
    ).scalars().all()
    hold_by_ticker = {h.ticker: h for h in hold_rows}

    rows: list[dict[str, Any]] = []
    for s in stocks:
        row: dict[str, Any] = {
            "_ticker": s.ticker,
            "sector": s.sector,
            "industry": s.industry,
            "market_cap_inr": s.market_cap_inr,
        }
        t = tech_by_ticker.get(s.ticker)
        if t is not None:
            for fn in _TECHNICALS_FIELDS:
                row[fn] = getattr(t, fn, None)
        h = hold_by_ticker.get(s.ticker)
        if h is not None:
            for fn in _HOLDINGS_FIELDS:
                row[fn] = getattr(h, fn, None)
        rows.append(row)
    return rows


async def run_screener(
    session: AsyncSession,
    expr_str: str,
    *,
    limit: int = 50,
    universe: list[str] | None = None,
) -> ScreenerResult:
    """Compile and evaluate an expression against the universe; return the
    matching tickers in deterministic order (alphabetic by symbol). The
    return shape mirrors `app/contracts/phase3.md::POST /screener/run`.
    """
    t0 = time.perf_counter()
    expr = compile_expr(expr_str)

    referenced: set[str] = set()
    _collect_referenced_fields(expr, referenced)

    rows = await _load_rows(session, universe=universe)
    universe_size = len(rows)

    matches = [r for r in rows if evaluate(expr, r)]
    matches.sort(key=lambda r: r["_ticker"])

    hits_fields = sorted(referenced)
    out_tickers: list[TickerHit] = []
    for r in matches[: max(0, limit)]:
        # v1 score: 1.0 for the head, decay linearly. A real scoring pass
        # belongs in A-3 once stored screeners ship.
        rank = len(out_tickers)
        denom = max(1, len(matches) - 1)
        score = round(1.0 - (rank / max(1.0, float(denom))), 4)
        out_tickers.append(
            TickerHit(
                symbol=r["_ticker"],
                score=score,
                hits=_row_to_str_dict(hits_fields, r),
            )
        )

    exec_ms = int((time.perf_counter() - t0) * 1000)
    return ScreenerResult(
        matched=len(matches),
        universe_size=universe_size,
        exec_ms=exec_ms,
        tickers=out_tickers,
    )


def result_to_dict(res: ScreenerResult) -> dict[str, Any]:
    """Match the locked REST shape from `app/contracts/phase3.md`."""
    return {
        "matched": res.matched,
        "universe_size": res.universe_size,
        "exec_ms": res.exec_ms,
        "tickers": [
            {"symbol": t.symbol, "score": t.score, "hits": t.hits}
            for t in res.tickers
        ],
    }
