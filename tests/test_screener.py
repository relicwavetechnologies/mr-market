"""Unit tests for the screener expression engine (P3-A2).

Layered coverage:
1. Tokeniser — every token kind, whitespace, multi-char ops, error cases.
2. Parser — comparators, AND, OR, NOT, parens, precedence, error cases.
3. Evaluator — numeric + string semantics, NULL handling.
4. Injection / safety — SQL-style payloads, attribute access, eval-bait.
5. Integration — `compile_expr` round trip + a couple of complex expressions.
6. Helper — `_collect_referenced_fields` returns exactly the fields used.

DB-side tests (`run_screener` against Postgres) live in
`tests/test_screener_db.py` and only run when a live `mrmarket` is up; the
two test files share no state.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.analytics.screener import (
    ALLOWED_FIELDS,
    And,
    Compare,
    Not,
    Or,
    ScreenerError,
    _collect_referenced_fields,
    compile_expr,
    evaluate,
    parse,
    tokenise,
)


# ---------------------------------------------------------------------------
# 1. Tokeniser
# ---------------------------------------------------------------------------


class TestTokenise:
    def test_simple_comparison(self):
        toks = tokenise("rsi_14 < 30")
        assert [t.kind for t in toks] == ["IDENT", "OP", "NUMBER"]
        assert [t.value for t in toks] == ["rsi_14", "<", "30"]

    def test_decimal_number(self):
        toks = tokenise("rsi_14 < 29.95")
        assert toks[2].value == "29.95"

    def test_negative_number(self):
        toks = tokenise("macd > -2.5")
        assert toks[2].value == "-2.5"

    def test_string_single_quoted(self):
        toks = tokenise("sector = 'Financial Services'")
        assert toks[2].kind == "STRING"
        assert toks[2].value == "Financial Services"

    def test_string_double_quoted(self):
        toks = tokenise('sector = "IT"')
        assert toks[2].kind == "STRING"
        assert toks[2].value == "IT"

    def test_multi_char_ops(self):
        for op in ["<=", ">=", "==", "!=", "<>"]:
            toks = tokenise(f"rsi_14 {op} 30")
            assert toks[1].value == op

    def test_parens_emitted(self):
        toks = tokenise("(rsi_14 < 30)")
        assert [t.kind for t in toks] == ["LPAREN", "IDENT", "OP", "NUMBER", "RPAREN"]

    def test_whitespace_irrelevant(self):
        a = tokenise("rsi_14<30")
        b = tokenise("  rsi_14   <    30   ")
        assert [t.value for t in a] == [t.value for t in b]

    def test_unrecognised_char_rejected(self):
        # Catches the obvious SQL-style payloads at the lex layer.
        for s in [
            "rsi_14 < 30; DROP TABLE stocks",
            "rsi_14 < 30 -- comment",
            "rsi_14 < 30 /* comment */",
            "rsi_14 < 30 | sector = 'IT'",
        ]:
            with pytest.raises(ScreenerError):
                tokenise(s)

    def test_empty_string_rejected(self):
        with pytest.raises(ScreenerError):
            tokenise("")
        with pytest.raises(ScreenerError):
            tokenise("   ")


# ---------------------------------------------------------------------------
# 2. Parser
# ---------------------------------------------------------------------------


class TestParse:
    def test_simple_comparison(self):
        expr = parse(tokenise("rsi_14 < 30"))
        assert expr == Compare(field="rsi_14", op="<", value=Decimal("30"))

    def test_and_chain(self):
        expr = parse(tokenise("rsi_14 < 30 AND promoter_pct > 50"))
        assert isinstance(expr, And)
        assert expr.left == Compare(field="rsi_14", op="<", value=Decimal("30"))
        assert expr.right == Compare(field="promoter_pct", op=">", value=Decimal("50"))

    def test_or_chain(self):
        expr = parse(tokenise("rsi_14 < 30 OR rsi_14 > 70"))
        assert isinstance(expr, Or)

    def test_not_unary(self):
        expr = parse(tokenise("NOT rsi_14 > 70"))
        assert isinstance(expr, Not)
        assert expr.inner == Compare(field="rsi_14", op=">", value=Decimal("70"))

    def test_double_not_collapses_in_eval_not_parse(self):
        # We don't optimise NOT NOT in the parser; both Nots are kept.
        expr = parse(tokenise("NOT NOT rsi_14 > 70"))
        assert isinstance(expr, Not)
        assert isinstance(expr.inner, Not)

    def test_precedence_and_binds_tighter_than_or(self):
        # a OR b AND c → a OR (b AND c)
        expr = parse(
            tokenise("rsi_14 < 30 OR rsi_14 > 70 AND promoter_pct > 50")
        )
        assert isinstance(expr, Or)
        assert isinstance(expr.right, And)

    def test_parens_override_precedence(self):
        # (a OR b) AND c → AND( OR(a,b), c )
        expr = parse(
            tokenise("(rsi_14 < 30 OR rsi_14 > 70) AND promoter_pct > 50")
        )
        assert isinstance(expr, And)
        assert isinstance(expr.left, Or)

    def test_keywords_case_insensitive(self):
        a = parse(tokenise("rsi_14 < 30 AND promoter_pct > 50"))
        b = parse(tokenise("rsi_14 < 30 and promoter_pct > 50"))
        c = parse(tokenise("rsi_14 < 30 And promoter_pct > 50"))
        assert a == b == c

    def test_identifier_case_normalised_to_lower(self):
        expr = parse(tokenise("RSI_14 < 30"))
        assert isinstance(expr, Compare)
        assert expr.field == "rsi_14"

    def test_unbalanced_parens_rejected(self):
        with pytest.raises(ScreenerError):
            parse(tokenise("(rsi_14 < 30"))
        with pytest.raises(ScreenerError):
            parse(tokenise("rsi_14 < 30)"))

    def test_missing_operator_rejected(self):
        with pytest.raises(ScreenerError):
            parse(tokenise("rsi_14 30"))

    def test_missing_value_rejected(self):
        with pytest.raises(ScreenerError):
            parse(tokenise("rsi_14 <"))

    def test_trailing_garbage_rejected(self):
        with pytest.raises(ScreenerError):
            parse(tokenise("rsi_14 < 30 promoter_pct > 50"))


# ---------------------------------------------------------------------------
# 3. Field allowlist
# ---------------------------------------------------------------------------


class TestFieldAllowlist:
    def test_unknown_field_rejected(self):
        with pytest.raises(ScreenerError, match="unknown field"):
            compile_expr("nonsense_field < 30")

    def test_python_dunder_field_rejected(self):
        # No way to reach __class__, __dict__, etc. via the allowlist.
        with pytest.raises(ScreenerError, match="unknown field"):
            compile_expr("__class__ = 'foo'")

    def test_known_fields_in_allowlist(self):
        for f in ("rsi_14", "promoter_pct", "sector", "close", "sma_200"):
            assert f in ALLOWED_FIELDS, f"expected {f} in ALLOWED_FIELDS"


# ---------------------------------------------------------------------------
# 4. Evaluator — numeric semantics
# ---------------------------------------------------------------------------


class TestEvaluateNumeric:
    @pytest.mark.parametrize(
        "expr_str,row,expected",
        [
            ("rsi_14 < 30", {"rsi_14": Decimal("28.4")}, True),
            ("rsi_14 < 30", {"rsi_14": Decimal("29.9999")}, True),
            ("rsi_14 < 30", {"rsi_14": Decimal("30")}, False),
            ("rsi_14 <= 30", {"rsi_14": Decimal("30")}, True),
            ("rsi_14 > 70", {"rsi_14": Decimal("75.1")}, True),
            ("rsi_14 >= 70", {"rsi_14": Decimal("70")}, True),
            ("rsi_14 = 50", {"rsi_14": Decimal("50.00")}, True),
            ("rsi_14 != 50", {"rsi_14": Decimal("50.0")}, False),
            ("rsi_14 != 50", {"rsi_14": Decimal("50.01")}, True),
            ("close > sma_200", {"close": Decimal("100")}, False),  # sma_200 missing
        ],
    )
    def test_comparison_semantics(self, expr_str, row, expected):
        # `close > sma_200` would actually fail tokenise because sma_200
        # is a field, not a number. Skip that case; replace with literal.
        if "sma_200" in expr_str:
            return  # tested separately below
        assert evaluate(compile_expr(expr_str), row) is expected

    def test_int_and_decimal_compare_correctly(self):
        # The row stores an int; the expr literal is decimal.
        assert evaluate(compile_expr("vol_avg_20 > 1000"), {"vol_avg_20": 5000}) is True
        assert evaluate(compile_expr("vol_avg_20 < 100"), {"vol_avg_20": 5000}) is False

    def test_float_in_row_works(self):
        # We accept floats in the row even though our DB stores Decimals.
        assert evaluate(compile_expr("rsi_14 < 30"), {"rsi_14": 28.4}) is True


# ---------------------------------------------------------------------------
# 5. Evaluator — NULL handling
# ---------------------------------------------------------------------------


class TestEvaluateNull:
    def test_compare_against_none_is_false(self):
        # Field present in row but None → comparison is False.
        for op in ("<", "<=", ">", ">=", "=", "!="):
            assert evaluate(
                compile_expr(f"rsi_14 {op} 30"), {"rsi_14": None}
            ) is False

    def test_missing_field_in_row_is_false(self):
        # Field not present at all → still False, never KeyError.
        assert evaluate(compile_expr("rsi_14 < 30"), {}) is False

    def test_not_against_none_inverts_to_true(self):
        # NOT (false) = True. Important: don't confuse the user.
        assert evaluate(compile_expr("NOT rsi_14 > 70"), {"rsi_14": None}) is True


# ---------------------------------------------------------------------------
# 6. Evaluator — string fields
# ---------------------------------------------------------------------------


class TestEvaluateString:
    def test_sector_equality(self):
        assert evaluate(
            compile_expr("sector = 'Financial Services'"),
            {"sector": "Financial Services"},
        ) is True

    def test_sector_inequality(self):
        assert evaluate(
            compile_expr("sector != 'IT'"), {"sector": "Financial Services"}
        ) is True
        assert evaluate(compile_expr("sector != 'IT'"), {"sector": "IT"}) is False

    def test_string_with_relational_op_rejected(self):
        # `<` / `<=` / `>` / `>=` against a string is a user error, not silently False.
        # Implementation: raises ScreenerError at evaluate time.
        with pytest.raises(ScreenerError):
            evaluate(compile_expr("sector < 'IT'"), {"sector": "Financial Services"})

    def test_unicode_string_compare(self):
        assert evaluate(
            compile_expr("sector = 'Énergie'"), {"sector": "Énergie"}
        ) is True


# ---------------------------------------------------------------------------
# 7. Boolean composition
# ---------------------------------------------------------------------------


class TestEvaluateBoolean:
    def test_and_short_circuits(self):
        row = {"rsi_14": Decimal("28")}  # missing promoter_pct
        # rsi_14 < 30 → True; promoter_pct > 50 → False (None) → AND False.
        assert evaluate(
            compile_expr("rsi_14 < 30 AND promoter_pct > 50"), row
        ) is False

    def test_or_recovers_from_left_false(self):
        row = {"rsi_14": Decimal("60"), "promoter_pct": Decimal("75")}
        assert evaluate(
            compile_expr("rsi_14 < 30 OR promoter_pct > 50"), row
        ) is True

    def test_complex_with_parens_and_not(self):
        # (rsi_14 < 30 AND promoter_pct > 50) OR NOT (sector = 'IT')
        row = {"rsi_14": Decimal("60"), "promoter_pct": Decimal("75"), "sector": "Energy"}
        expr = compile_expr(
            "(rsi_14 < 30 AND promoter_pct > 50) OR NOT (sector = 'IT')"
        )
        assert evaluate(expr, row) is True  # IT-negated branch satisfied

    def test_double_not_returns_original(self):
        assert evaluate(
            compile_expr("NOT NOT rsi_14 < 30"), {"rsi_14": Decimal("28")}
        ) is True


# ---------------------------------------------------------------------------
# 8. Injection rejection — defence-in-depth at every layer
# ---------------------------------------------------------------------------


class TestInjectionResistance:
    @pytest.mark.parametrize(
        "payload",
        [
            "rsi_14 < 30; DELETE FROM stocks",
            "rsi_14 < 30 -- '",
            "rsi_14 < 30 /* */",
            "1=1",
            "True",
            "__import__('os').system('rm -rf /')",
            "'; SELECT 1; --",
            "rsi_14 < 30 UNION SELECT * FROM users",
        ],
    )
    def test_payloads_rejected(self, payload):
        with pytest.raises(ScreenerError):
            compile_expr(payload)

    def test_no_python_eval_path(self):
        # The engine must not call eval/exec under any circumstance.
        # If evaluate() ever did, this row {'__class__': str} would
        # provoke a Python-side comparison error.
        # Field allowlist already prevents this — sanity check it stays so.
        with pytest.raises(ScreenerError):
            compile_expr("__class__ = 'str'")


# ---------------------------------------------------------------------------
# 9. _collect_referenced_fields — used by the hits serializer
# ---------------------------------------------------------------------------


class TestCollectReferencedFields:
    def test_simple_expression(self):
        out: set[str] = set()
        _collect_referenced_fields(compile_expr("rsi_14 < 30"), out)
        assert out == {"rsi_14"}

    def test_multiple_fields_dedup(self):
        out: set[str] = set()
        _collect_referenced_fields(
            compile_expr("rsi_14 < 30 AND rsi_14 > 10 AND promoter_pct > 50"),
            out,
        )
        assert out == {"rsi_14", "promoter_pct"}

    def test_nested_with_not_and_parens(self):
        out: set[str] = set()
        _collect_referenced_fields(
            compile_expr(
                "(rsi_14 < 30 OR sector = 'IT') AND NOT promoter_pct > 50"
            ),
            out,
        )
        assert out == {"rsi_14", "sector", "promoter_pct"}


# ---------------------------------------------------------------------------
# 10. Round-trip / public API smoke
# ---------------------------------------------------------------------------


class TestFieldToField:
    """`close > sma_200` — RHS is another allow-listed field."""

    def test_parses_field_to_field(self):
        from app.analytics.screener import FieldRef

        expr = compile_expr("close > sma_200")
        assert isinstance(expr, Compare)
        assert expr.field == "close"
        assert expr.op == ">"
        assert isinstance(expr.value, FieldRef)
        assert expr.value.name == "sma_200"

    def test_evaluates_close_above_sma200(self):
        row = {"close": Decimal("100"), "sma_200": Decimal("90")}
        assert evaluate(compile_expr("close > sma_200"), row) is True
        row = {"close": Decimal("80"), "sma_200": Decimal("90")}
        assert evaluate(compile_expr("close > sma_200"), row) is False

    def test_field_to_field_with_missing_rhs_is_false(self):
        # RHS field absent → None → comparison False (NULL semantics).
        assert evaluate(compile_expr("close > sma_200"), {"close": Decimal("100")}) is False

    def test_field_to_field_with_missing_lhs_is_false(self):
        assert evaluate(compile_expr("close > sma_200"), {"sma_200": Decimal("90")}) is False

    def test_unknown_rhs_field_rejected(self):
        with pytest.raises(ScreenerError, match="unknown field"):
            compile_expr("close > ghost_field")

    def test_field_to_field_with_and(self):
        row = {
            "rsi_14": Decimal("70"),
            "close": Decimal("100"),
            "sma_50": Decimal("90"),
            "sma_200": Decimal("80"),
        }
        assert evaluate(
            compile_expr("rsi_14 > 65 AND close > sma_50 AND close > sma_200"),
            row,
        ) is True

    def test_collected_fields_include_rhs(self):
        out: set[str] = set()
        _collect_referenced_fields(compile_expr("close > sma_200"), out)
        assert out == {"close", "sma_200"}


class TestPublicApi:
    def test_compile_then_evaluate(self):
        row = {
            "rsi_14": Decimal("28.4"),
            "promoter_pct": Decimal("50.5"),
            "sector": "Financial Services",
        }
        assert evaluate(
            compile_expr(
                "rsi_14 < 30 AND promoter_pct > 50 AND sector = 'Financial Services'"
            ),
            row,
        ) is True
