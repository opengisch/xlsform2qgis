import re

import pytest

from xlsform2qgis.expressions.expression import (
    Expression,
    ExpressionContext,
    QgisRenderType,
    format_date_codes,
)
from xlsform2qgis.expressions.parser import ParseError, ParserType


def build_context(
    expressions: dict[str, str] | None = None,
    parser_type: ParserType = ParserType.EXPRESSION,
) -> ExpressionContext:
    context = ExpressionContext(
        current_field="field001",
        calculate_expressions={
            "calc_field": Expression(
                "10 + 5 + random()",
                ExpressionContext(
                    current_field="calc_field",
                    calculate_expressions={},
                    parser_type=parser_type,
                ),
            )
        },
        parser_type=parser_type,
    )
    if expressions:
        for name, expr in expressions.items():
            context.calculate_expressions[name] = Expression(expr, context)

    return context


@pytest.fixture
def ctx() -> ExpressionContext:
    return build_context()


@pytest.mark.parametrize(
    ["xls_format", "expected"],
    [
        ("%Y-%m-%d", "yyyy-MM-dd"),
        ("%y/%n/%e", "yy/M/d"),
        ("%a, %b %d", "ddd, MMM dd"),
        ("Date: %Y_%m_%d at %a", "Date: yyyy_MM_dd at ddd"),
        ("plain-text", "plain-text"),
        ("%Y %Y %m", "yyyy yyyy MM"),
    ],
)
def test_format_date_codes(xls_format: str, expected: str) -> None:
    assert format_date_codes(xls_format) == expected


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
def test_render_literals_and_variables(
    expression: str, expected: str, ctx: ExpressionContext
) -> None:
    expr = Expression(expression, ctx)
    assert expr.to_qgis() == expected


def test_selected_function_conversion(ctx) -> None:
    expr = Expression("selected(${choice}, 'value')", ctx)
    assert (
        expr.to_qgis()
        == """
if(
    /* guess whether the value is a multiple selection. Assumptions: values does not contain `,`, `}` or `{` (comma or curly brace) characters */
    rtrim(ltrim( "choice", '{'), '}' ) = "choice",
    /* if it is not a multiple selection, just check for equality */
    "choice" = 'value',
    /* if it is a multiple selection, check if the selected value is in the array of selected values */
    array_contains( array_foreach( string_to_array( rtrim(ltrim( "choice", '{'), '}' ), ',' ), substr(@element, 2, -1) ), 'value' )
)
""".strip()
    )


def test_regex_function_conversion(ctx) -> None:
    expr = Expression("regex(${field}, '^[0-9]+$')", ctx)
    assert expr.to_qgis() == "regexp_match(\"field\", '^[0-9]+$')"


def test_today_function_conversion(ctx) -> None:
    expr = Expression("today()", ctx)
    assert expr.to_qgis() == "format_date(now(), 'yyyy-MM-dd')"


def test_true_false_literals(ctx) -> None:
    assert Expression("true()", ctx).to_qgis() == "true"
    assert Expression("false()", ctx).to_qgis() == "false"


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1 + 2 * 3", "1 + 2 * 3"),
        ("(1 + 2) * 3", "(1 + 2) * 3"),
        ("1 - (2 - 3)", "1 - (2 - 3)"),
        ("(1 - 2) - 3", "1 - 2 - 3"),
        ("1 + 2 + 3", "1 + 2 + 3"),
        ("1 * 2 div 3", "1 * 2 / 3"),
        ("1 * 2 mod 3", "1 * 2 % 3"),
        ("1 + 2 * 3 = 7", "1 + 2 * 3 = 7"),
        ("1 + 2 * 3 > 7 and 4 < 5", "1 + 2 * 3 > 7 and 4 < 5"),
        ("1 = 1 or 2 = 2 and 3 = 3", "1 = 1 or 2 = 2 and 3 = 3"),
        ("(1 = 1 or 2 = 2) and 3 = 3", "(1 = 1 or 2 = 2) and 3 = 3"),
    ],
)
def test_binary_precedence_and_parentheses(
    expression: str, expected: str, ctx: ExpressionContext
) -> None:
    expr = Expression(expression, ctx)
    assert expr.to_qgis() == expected


def test_unary_operator_parentheses(ctx: ExpressionContext) -> None:
    expr = Expression("-(1 + 2)", ctx)
    assert expr.to_qgis() == "- (1 + 2)"


def test_nested_function_composition(ctx: ExpressionContext) -> None:
    expr = Expression("selected(${choice1}, 'value') and regex(${choice2}, 'b')", ctx)
    assert (
        expr.to_qgis()
        == """if(
    /* guess whether the value is a multiple selection. Assumptions: values does not contain `,`, `}` or `{` (comma or curly brace) characters */
    rtrim(ltrim( "choice1", '{'), '}' ) = "choice1",
    /* if it is not a multiple selection, just check for equality */
    "choice1" = 'value',
    /* if it is a multiple selection, check if the selected value is in the array of selected values */
    array_contains( array_foreach( string_to_array( rtrim(ltrim( "choice1", '{'), '}' ), ',' ), substr(@element, 2, -1) ), 'value' )
) and regexp_match(\"choice2\", 'b')"""
    )


def test_calculate_expression_substitution() -> None:
    ctx = build_context({"calc": "10 + 5"})
    expr = Expression("${calc} * 2", ctx)
    assert expr.to_qgis() == "(10 + 5) * 2"


def test_calculate_expression_cycle_fallbacks_to_field_name() -> None:
    ctx = build_context({"calc": "${calc} + 1"})
    expr = Expression("${calc}", ctx)
    assert expr.to_qgis() == '"calc" + 1'


def test_bracket_list_rendering(ctx: ExpressionContext) -> None:
    expr = Expression("(1, 2, 3)", ctx)
    assert expr.to_qgis() == "(1, 2, 3)"


def test_complex_expression_rendering(ctx: ExpressionContext) -> None:
    expr = Expression(
        r"""regex( substring-before(${field001}, "world"), '$\{hello')""", ctx
    )
    assert (
        expr.to_qgis()
        == """regexp_match(substr("field001", 1, strpos("field001", 'world')), '$\\{hello')"""
    )


def test_fails_on_unsupported_operator(ctx: ExpressionContext) -> None:
    with pytest.raises(ValueError, match=re.escape("Unexpected character: ^")):
        Expression("1 ^ 2", ctx)


def test_raises_on_non_existent_function(ctx: ExpressionContext) -> None:
    with pytest.raises(
        ParseError, match=re.escape("Unknown function `dynamic_function`")
    ):
        Expression("dynamic_function(${field})", ctx)


def test_empty_expression(ctx: ExpressionContext) -> None:
    assert Expression("", ctx).to_qgis() == ""
    assert Expression("   ", ctx).to_qgis() == ""


def test_not_supported_xlsform_function(ctx: ExpressionContext) -> None:
    with pytest.raises(
        ParseError,
        match=re.escape("Function not supported in QGIS expressions `digest`"),
    ):
        Expression("digest('abcd', 'key')", ctx)


def test_curly_quote_normalization(ctx: ExpressionContext) -> None:
    assert Expression("'text' and 'more'", ctx).to_qgis() == "'text' and 'more'"


def test_dot_replacement_with_field_name(ctx: ExpressionContext) -> None:
    assert Expression(". > 5", ctx).to_qgis() == '"field001" > 5'
    assert Expression("(.) > 5", ctx).to_qgis() == '"field001" > 5'
    assert Expression(". = 10", ctx).to_qgis() == '"field001" = 10'


def test_simple_field_reference(ctx: ExpressionContext) -> None:
    assert Expression("${field}", ctx).to_qgis() == '"field"'
    assert Expression("${my_field}", ctx).to_qgis() == '"my_field"'


def test_string_length_conversion(ctx: ExpressionContext) -> None:
    assert Expression("string-length(${name})", ctx).to_qgis() == 'length("name")'
    assert Expression("string-length( ${field} )", ctx).to_qgis() == 'length("field")'
    assert (
        Expression("string-length( substr(${field}, 1, 10) )", ctx).to_qgis()
        == 'length(substr("field", 1 + 1, 10))'
    )


def test_use_expression_with_current_value(ctx: ExpressionContext) -> None:
    assert (
        Expression("${field}", ctx).to_qgis(use_current=True)
        == "current_value('field')"
    )


def test_use_template_without_current_value() -> None:
    ctx = build_context(parser_type=ParserType.TEMPLATE)

    assert (
        Expression("hello ${field} world", ctx).to_qgis(
            expression_type=QgisRenderType.EXPRESSION
        )
        == "'hello ' || \"field\" || ' world'"
    )
    assert (
        Expression("hello ${field} world", ctx).to_qgis(
            expression_type=QgisRenderType.TEMPLATE
        )
        == 'hello [% "field" %] world'
    )


def test_use_template_with_current_value() -> None:
    ctx = build_context(parser_type=ParserType.TEMPLATE)

    assert (
        Expression("Hello ${field} world", ctx).to_qgis(
            use_current=True, expression_type=QgisRenderType.EXPRESSION
        )
        == r"'Hello ' || current_value('field') || ' world'"
    )

    assert (
        Expression("Hello ${field} world", ctx).to_qgis(
            use_current=True, expression_type=QgisRenderType.TEMPLATE
        )
        == r"Hello [% current_value('field') %] world"
    )


def test_use_template_substitutes_calculate_expression() -> None:
    ctx = build_context(
        parser_type=ParserType.TEMPLATE,
        expressions={"greeting": "Hello ${name}"},
    )

    assert (
        Expression("${greeting}", ctx).to_qgis(expression_type=QgisRenderType.TEMPLATE)
        == 'Hello [% "name" %]'
    )


def test_use_template_cycle_fallbacks_to_field_name() -> None:
    ctx = build_context(
        parser_type=ParserType.TEMPLATE,
        expressions={"loop": "${loop}"},
    )

    assert (
        Expression("${loop}", ctx).to_qgis(expression_type=QgisRenderType.TEMPLATE)
        == '"loop"'
    )


def test_expressions_substitution(ctx: ExpressionContext) -> None:
    assert Expression("${calc_field} * 2", ctx).to_qgis() == "(10 + 5 + randf()) * 2"


def test_complex_expression(ctx: ExpressionContext) -> None:
    assert (
        Expression("${age} > 18 and ${name} != ''", ctx).to_qgis()
        == '"age" > 18 and "name" != \'\''
    )


def test_multiple_field_references(ctx: ExpressionContext) -> None:
    assert Expression("${field1} + ${field2}", ctx).to_qgis() == '"field1" + "field2"'


def test_nested_selected_functions(ctx: ExpressionContext) -> None:
    assert (
        Expression("int(number(${choice}))", ctx).to_qgis()
        == 'to_int(to_real("choice"))'
    )


def test_concatenate_function(ctx: ExpressionContext) -> None:
    assert Expression("concat(${first_name})", ctx).to_qgis() == 'concat("first_name")'
    assert (
        Expression("concat(${first_name}, ' ', ${last_name})", ctx).to_qgis()
        == 'concat("first_name", \' \', "last_name")'
    )


def test_is_str_with_literal_string(ctx: ExpressionContext) -> None:
    assert Expression("'hello'", ctx).is_str() is True


def test_is_str_with_literal_number(ctx: ExpressionContext) -> None:
    assert Expression("123", ctx).is_str() is False


def test_is_str_with_template_only_strings() -> None:
    template_ctx = build_context(parser_type=ParserType.TEMPLATE)
    assert Expression("Hello world", template_ctx).is_str() is True


def test_is_str_with_template_including_variable() -> None:
    template_ctx = build_context(parser_type=ParserType.TEMPLATE)
    assert Expression("Hello ${name}", template_ctx).is_str() is False
