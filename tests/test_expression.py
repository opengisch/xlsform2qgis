import pytest

from xlsform2qgis.expressions.expression import Expression, ExpressionContext


def build_context(expressions: dict[str, str] | None = None) -> ExpressionContext:
    context = ExpressionContext(calculate_expressions={}, current_field="field001")
    if expressions:
        for name, expr in expressions.items():
            context.calculate_expressions[name] = Expression(expr, context)
    return context


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1", "1"),
        ("3.14", "3.14"),
        ("'text'", "'text'"),
        ('"text"', "'text'"),
        (r"${field}", '"field"'),
        ("foo", "foo"),
        (".", '"field001"'),
    ],
)
def test_render_literals_and_variables(expression: str, expected: str) -> None:
    ctx = build_context()
    expr = Expression(expression, ctx)
    assert expr.to_qgis_expression() == expected


def test_selected_function_conversion() -> None:
    ctx = build_context()
    expr = Expression("selected(${choice}, 'value')", ctx)
    assert expr.to_qgis_expression() == "\"choice\" = 'value'"


def test_regex_function_conversion() -> None:
    ctx = build_context()
    expr = Expression("regex(${field}, '^[0-9]+$')", ctx)
    assert expr.to_qgis_expression() == "regexp_match(\"field\", '^[0-9]+$')"


def test_today_function_conversion() -> None:
    ctx = build_context()
    expr = Expression("today()", ctx)
    assert expr.to_qgis_expression() == "format_date(now(), 'yyyy-MM-dd')"


def test_string_length_conversion() -> None:
    ctx = build_context()
    expr = Expression("string-length(${name})", ctx)
    assert expr.to_qgis_expression() == 'length("name")'


def test_true_false_literals() -> None:
    ctx = build_context()
    assert Expression("true()", ctx).to_qgis_expression() == "true"
    assert Expression("false()", ctx).to_qgis_expression() == "false"


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1 + 2 * 3", "1 + 2 * 3"),
        ("(1 + 2) * 3", "(1 + 2) * 3"),
        ("1 - (2 - 3)", "1 - (2 - 3)"),
        ("(1 - 2) - 3", "1 - 2 - 3"),
        ("1 + 2 + 3", "1 + 2 + 3"),
        ("1 * 2 div 3", "1 * 2 div 3"),
        ("1 + 2 * 3 = 7", "1 + 2 * 3 = 7"),
        ("1 + 2 * 3 > 7 and 4 < 5", "1 + 2 * 3 > 7 and 4 < 5"),
        ("1 = 1 or 2 = 2 and 3 = 3", "1 = 1 or 2 = 2 and 3 = 3"),
        ("(1 = 1 or 2 = 2) and 3 = 3", "(1 = 1 or 2 = 2) and 3 = 3"),
    ],
)
def test_binary_precedence_and_parentheses(expression: str, expected: str) -> None:
    ctx = build_context()
    expr = Expression(expression, ctx)
    assert expr.to_qgis_expression() == expected


def test_unary_operator_parentheses() -> None:
    ctx = build_context()
    expr = Expression("-(1 + 2)", ctx)
    assert expr.to_qgis_expression() == "- (1 + 2)"


def test_nested_function_composition() -> None:
    ctx = build_context()
    expr = Expression("selected(${choice1}, 'a') and regex(${choice2}, 'b')", ctx)
    assert (
        expr.to_qgis_expression()
        == "\"choice1\" = 'a' and regexp_match(\"choice2\", 'b')"
    )


def test_calculate_expression_substitution() -> None:
    ctx = build_context({"calc": "10 + 5"})
    expr = Expression("${calc} * 2", ctx)
    assert expr.to_qgis_expression() == "(10 + 5) * 2"


def test_calculate_expression_cycle_fallbacks_to_field_name() -> None:
    ctx = build_context({"calc": "${calc} + 1"})
    expr = Expression("${calc}", ctx)
    assert expr.to_qgis_expression() == '"calc" + 1'


def test_bracket_list_rendering() -> None:
    ctx = build_context()
    expr = Expression("(1, 2, 3)", ctx)
    assert expr.to_qgis_expression() == "(1, 2, 3)"


def test_complex_expression_rendering() -> None:
    ctx = build_context()
    expr = Expression(
        r"""regex( substring-before(${field001}, "world"), '$\{hello')""", ctx
    )
    assert (
        expr.to_qgis_expression()
        == """regexp_match(substr("field001", 1, strpos("field001", 'world')), '$\\{hello')"""
    )
