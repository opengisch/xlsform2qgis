from typing import assert_never
from dataclasses import dataclass
from enum import StrEnum

from xlsform2qgis.expressions.parser import (
    AstNode,
    BinaryOp,
    BracketList,
    Call,
    Current,
    Identifier,
    Literal,
    LiteralType,
    UnaryOp,
    Variable,
    Template,
    parse_expression,
    parse_template,
    ParserType,
)
from xlsform2qgis.converter_utils import strip_tags


class QgisRenderType(StrEnum):
    TEMPLATE = "template"
    EXPRESSION = "expression"


@dataclass
class ExpressionContext:
    current_field: str
    calculate_expressions: dict[str, "Expression"]
    parser_type: ParserType


@dataclass(frozen=True)
class QgisExpressionSpec:
    expression: str = ""


class ExpressionError(Exception): ...


TEMPLATE_START = "[% "
TEMPLATE_END = " %]"
SUPPORTED_FUNCTIONS_BY_QGIS: dict[str, QgisExpressionSpec | None] = {
    "if": QgisExpressionSpec("if({1}, {2}, {3})"),
    "position": None,
    "once": None,
    "selected": QgisExpressionSpec(
        # Because we will use `str().format()`, we need to escape the curly braces in the QGIS expression by doubling them, and we also need to use {1}, {2} etc. as placeholders for the arguments
        """
if(
    /* guess whether the value is a multiple selection. Assumptions: values does not contain `,`, `}}` or `{{` (comma or curly brace) characters */
    rtrim(ltrim( {1}, '{{'), '}}' ) = {1},
    /* if it is not a multiple selection, just check for equality */
    {1} = {2},
    /* if it is a multiple selection, check if the selected value is in the array of selected values */
    array_contains( array_foreach( string_to_array( rtrim(ltrim( {1}, '{{'), '}}' ), ',' ), substr(@element, 2, -1) ), {2} )
)
    """.strip()
    ),
    "selected-at": QgisExpressionSpec("coalesce(array_get({1}, {2}), '')"),
    "count-selected": QgisExpressionSpec("array_length({1})"),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#jr-choice-name
    "jr:choice-name": None,
    "indexed-repeat": None,
    "count": QgisExpressionSpec("array_length({1})"),
    "count-non-empty": QgisExpressionSpec("array_length({1}) - count_missing({1})"),
    "sum": QgisExpressionSpec("array_sum({1})"),
    "max": QgisExpressionSpec("array_max({1})"),
    "min": QgisExpressionSpec("array_min({1})"),
    "regex": QgisExpressionSpec("regexp_match({1}, {2})"),
    "contains": QgisExpressionSpec("strpos({1}, {2}) > 0"),
    "starts-with": QgisExpressionSpec("left({1}, length({2})) = {2}"),
    "ends-with": QgisExpressionSpec("right({1}, length({2})) = {2}"),
    "substr": QgisExpressionSpec("substr({1}, {2} + 1, {3})"),
    "substring-before": QgisExpressionSpec("substr({1}, 1, strpos({1}, {2}))"),
    "substring-after": QgisExpressionSpec("substr({1}, strpos({1}, {2}) + 1)"),
    "translate": QgisExpressionSpec(
        "array_foreach(string_to_array({2}, ''), replace({1}, @element, coalesce(array_get(string_to_array({2}, ''), @counter), '')))"
    ),
    "string-length": QgisExpressionSpec("length({1})"),
    "normalize-space": QgisExpressionSpec("trim(  regexp_replace( {1}, '\\s+', ' ') )"),
    "concat": QgisExpressionSpec("concat({1}, {2})"),
    "join": QgisExpressionSpec("array_to_string({1}, {2})"),
    "boolean-from-string": QgisExpressionSpec("{1} == 'true' or {1} == '1'"),
    "string": QgisExpressionSpec("to_string({1})"),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#digest
    "digest": None,
    "base64-decode": QgisExpressionSpec("from_base64({1})"),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#extract-signed
    "extract-signed": None,
    "round": QgisExpressionSpec("round({1}, {2})"),
    "int": QgisExpressionSpec("to_int({1})"),
    "number": QgisExpressionSpec("to_real({1})"),
    "pow": QgisExpressionSpec("{1} ^ {2}"),
    "log": QgisExpressionSpec("ln({1})"),
    "log10": QgisExpressionSpec("log({1})"),
    "abs": QgisExpressionSpec("abs({1})"),
    "sin": QgisExpressionSpec("sin({1})"),
    "cos": QgisExpressionSpec("cos({1})"),
    "tan": QgisExpressionSpec("tan({1})"),
    "asin": QgisExpressionSpec("asin({1})"),
    "acos": QgisExpressionSpec("acos({1})"),
    "atan": QgisExpressionSpec("atan({1})"),
    "atan2": QgisExpressionSpec("atan2({1}, {2})"),
    "sqrt": QgisExpressionSpec("sqrt({1})"),
    "exp": QgisExpressionSpec("exp({1})"),
    "exp10": QgisExpressionSpec("10 ^ {1}"),
    "pi": QgisExpressionSpec("pi()"),
    "today": QgisExpressionSpec("format_date(now(), 'yyyy-MM-dd')"),
    "now": QgisExpressionSpec("now()"),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#converting-dates-and-time
    "decimal-date-time": None,
    "date": None,
    "decimal-time": None,
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#format-date
    "format-date": None,
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#format-date-time
    "format-date-time": None,
    "area": QgisExpressionSpec("area({1})"),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#distance
    "distance": None,
    "geofence": QgisExpressionSpec("contains({2}, {1})"),
    "random": QgisExpressionSpec("randf()"),
    "randomize": QgisExpressionSpec("array_get({1}, rand(0, array_length({1}) - 1))"),
    "uuid": QgisExpressionSpec(
        "if({1}, substr(repeat( uuid(format:='WithoutBraces'), ceil({1} / 32) ), 1, {1}), uuid(format:='WithoutBraces'))"
    ),
    "boolean": QgisExpressionSpec("to_bool({1})"),
    "not": QgisExpressionSpec("not {1}"),
    "coalesce": QgisExpressionSpec("coalesce({1}, {2})"),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#checklist
    "checklist": None,
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#weighted-checklist
    "weighted-checklist": None,
    "true": QgisExpressionSpec("true"),
    "false": QgisExpressionSpec("false"),
    # TODO @suricactus: implement https://xlsform.org/en/#how-to-pull-data-from-csv
    "pulldata": None,
}


def format_date_codes(xlsform_format: str) -> str:
    conversion_map = {
        r"%Y": "yyyy",
        r"%y": "yy",
        r"%m": "MM",
        r"%n": "M",
        r"%b": "MMM",
        r"%d": "dd",
        r"%e": "d",
        r"%a": "ddd",
    }

    for xls_code, qgis_code in conversion_map.items():
        xlsform_format = xlsform_format.replace(xls_code, qgis_code)

    return xlsform_format


class Expression:
    def __init__(
        self,
        expression_str: str,
        context: ExpressionContext,
        *,
        should_strip_tags: bool = False,
    ):
        if should_strip_tags:
            expression_str = strip_tags(expression_str)

        self.expression_str = expression_str
        self.context = context

        if self.context.parser_type == ParserType.TEMPLATE:
            self.ast = parse_template(expression_str)
        else:
            self.ast = parse_expression(expression_str)

    def to_qgis(
        self,
        use_current: bool = False,
        expression_type: QgisRenderType = QgisRenderType.EXPRESSION,
    ) -> str:
        def wrap_field(field_name: str) -> str:
            return f'"{field_name}"'

        def render_tmpl(node: AstNode, seen: set[str]) -> tuple[str, int]:
            assert expression_type != QgisRenderType.EXPRESSION, (
                "render_tmpl should only be used for TEMPLATE expressions"
            )

            if isinstance(node, Template):
                elements = [render_tmpl(arg, seen)[0] for arg in node.elements]
                joined = "".join(elements)

                return joined, 100

            if isinstance(node, Literal):
                # in template context, we only have strings and empty literals, and we want to preserve the quotes if they are part of the string
                assert node.type == LiteralType.STRING

                return node.value, 100

            if isinstance(node, Variable):
                if node.name in seen:
                    return wrap_field(node.name), 100

                calculate_expr = self.context.calculate_expressions.get(node.name)
                if calculate_expr is not None:
                    seen.add(node.name)
                    rendered, prec = render_tmpl(calculate_expr.ast, seen)
                    seen.remove(node.name)
                    return rendered, prec

                if use_current:
                    field_expr = f"current_value('{node.name}')"
                else:
                    field_expr = wrap_field(node.name)

                return TEMPLATE_START + field_expr + TEMPLATE_END, 100

            # pragma: no cover
            return "", 100

        def render(node: AstNode, seen: set[str]) -> tuple[str, int]:
            # regular render should never encounter Template nodes, but we add an assertion here just to be safe
            if isinstance(node, Template):
                return " || ".join(render(arg, seen)[0] for arg in node.elements), 100

            if isinstance(node, Literal):
                if node.type == LiteralType.EMPTY:
                    return "", 100

                if node.type == LiteralType.STRING:
                    return f"'{node.value}'", 100

                return node.raw_value, 100

            if isinstance(node, Variable):
                if node.name in seen:
                    return wrap_field(node.name), 100

                calculate_expr = self.context.calculate_expressions.get(node.name)
                if calculate_expr is not None:
                    seen.add(node.name)
                    rendered, prec = render(calculate_expr.ast, seen)
                    seen.remove(node.name)
                    return rendered, prec

                if use_current:
                    return f"current_value('{node.name}')", 100
                else:
                    return wrap_field(node.name), 100

            if isinstance(node, Current):
                return wrap_field(self.context.current_field), 100

            if isinstance(node, Identifier):
                return node.raw_value, 100

            if isinstance(node, UnaryOp):
                operand, operand_prec = render(node.operand, seen)
                if operand_prec < 60:
                    operand = f"({operand})"
                return f"{node.operator} {operand}", 60

            if isinstance(node, BinaryOp):
                left, left_prec = render(node.left, seen)
                right, right_prec = render(node.right, seen)
                operator = _binary_operator(node.operator)
                prec = _binary_precedence(node.operator)

                if left_prec < prec:
                    left = f"({left})"
                if right_prec < prec or (
                    right_prec == prec and node.operator in _non_associative_ops()
                ):
                    right = f"({right})"

                return f"{left} {operator} {right}", prec

            if isinstance(node, Call):
                return render_call(node, seen)

            if isinstance(node, BracketList):
                elements = [render(arg, seen)[0] for arg in node.elements]
                joined = ", ".join(elements)
                return f"{node.open_bracket}{joined}{node.close_bracket}", 100

            # pragma: no cover
            return "", 100

        def render_call(node: Call, seen: set[str]) -> tuple[str, int]:
            rendered_args = [render(arg, seen)[0] for arg in node.args]

            assert isinstance(node.callee, Identifier)

            callee = node.callee.name

            # the parser should already have raised an error for unknown functions
            assert callee in SUPPORTED_FUNCTIONS_BY_QGIS

            qgis_spec = SUPPORTED_FUNCTIONS_BY_QGIS[callee]

            if qgis_spec is None:
                raise ExpressionError(
                    "Conversion of xlsform function not supported", node
                )

            qgis_expr = qgis_spec.expression.format(callee, *rendered_args)

            return qgis_expr, 100

        def _binary_precedence(operator: str) -> int:
            return {
                "or": 10,
                "and": 20,
                "=": 30,
                "!=": 30,
                ">": 30,
                ">=": 30,
                "<": 30,
                "<=": 30,
                "+": 40,
                "-": 40,
                "*": 50,
                "/": 50,
                "div": 50,
                "mod": 50,
            }.get(operator, 50)

        def _non_associative_ops() -> set[str]:
            return {"-", "/", "div", "mod", "=", "!=", ">", ">=", "<", "<="}

        def _binary_operator(operator: str) -> str:
            if operator == "div":
                return "/"
            if operator == "mod":
                return "%"
            return operator

        if expression_type == QgisRenderType.TEMPLATE:
            return render_tmpl(self.ast, set())[0]
        elif expression_type == QgisRenderType.EXPRESSION:
            return render(self.ast, set())[0]
        else:  # pragma: no cover
            assert_never(expression_type)

            raise NotImplementedError(
                f"Unknown parser type: {self.context.parser_type}"
            )

    def is_str(self) -> bool:
        if isinstance(self.ast, Template) and all(
            isinstance(elem, Literal) and elem.type == LiteralType.STRING
            for elem in self.ast.elements
        ):
            return True

        if isinstance(self.ast, Literal) and self.ast.type == LiteralType.STRING:
            return True

        return False
