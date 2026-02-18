from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from json2qgis.type_defs import ChoicesDef

from xlsform2qgis.converter_utils import strip_html
from xlsform2qgis.expressions.parser import (
    SUPPORTED_FUNCTIONS,
    AstNode,
    BinaryOp,
    BracketList,
    Call,
    Current,
    Identifier,
    Literal,
    LiteralType,
    ParserType,
    Template,
    UnaryOp,
    Variable,
    parse_expression,
    parse_template,
)
from xlsform2qgis.expressions.utils import SINGLE_QUOTE, wrap_field
from xlsform2qgis.type_defs import XlsformSettings


class QgisRenderType(StrEnum):
    TEMPLATE = "template"
    EXPRESSION = "expression"


@dataclass
class ExpressionContext:
    current_field: str
    calculate_expressions: dict[str, "Expression"]
    parser_type: ParserType
    choices_by_list: dict[str, list[ChoicesDef]]
    survey_settings: XlsformSettings
    skip_expression_errors: bool = False


class ExpressionError(Exception): ...


TEMPLATE_START = "[% "
TEMPLATE_END = " %]"


class Expression:
    def __init__(
        self,
        expression_str: str,
        context: ExpressionContext,
        *,
        should_strip_tags: bool = False,
    ):
        if should_strip_tags:
            expression_str = strip_html(expression_str)

        self.expression_str = expression_str
        self.context = context

        if self.context.parser_type == ParserType.TEMPLATE:
            self.ast = parse_template(expression_str)
        else:
            self.ast = parse_expression(expression_str)

    def _to_qgis(
        self,
        use_current: bool = False,
        expression_type: QgisRenderType = QgisRenderType.EXPRESSION,
    ) -> str:
        def get_field_value(field_name: str) -> str:
            if use_current:
                return f"current_value({wrap_field(field_name, SINGLE_QUOTE)})"
            else:
                return wrap_field(field_name)

        def render_tmpl(node: AstNode, seen: set[str]) -> tuple[str, int]:
            if expression_type == QgisRenderType.EXPRESSION:
                raise AssertionError(
                    "`render_tmpl` should only be used for `TEMPLATE` expressions"
                )

            if isinstance(node, Template):
                elements = [render_tmpl(arg, seen)[0] for arg in node.elements]
                joined = "".join(elements)

                return joined, 100

            if isinstance(node, Literal):
                if node.type not in (LiteralType.STRING, LiteralType.EMPTY):
                    raise AssertionError(
                        f"Unexpected literal type in template expression: {node.type}"
                    )

                return node.value, 100

            if isinstance(node, Variable):
                if node.name in seen:
                    field_expr = get_field_value(node.name)
                    return TEMPLATE_START + field_expr + TEMPLATE_END, 100

                calculate_expr = self.context.calculate_expressions.get(node.name)
                if calculate_expr is not None:
                    seen.add(node.name)
                    rendered, prec = render_tmpl(calculate_expr.ast, seen)
                    seen.remove(node.name)
                    return rendered, prec

                field_expr = get_field_value(node.name)
                return TEMPLATE_START + field_expr + TEMPLATE_END, 100

            raise AssertionError(
                f"Unexpected node type in template expression: {type(node)}"
            )

        def render(node: AstNode, seen: set[str]) -> tuple[str, int]:
            # regular render should never encounter Template nodes, but we add an assertion here just to be safe
            if isinstance(node, Template):
                return " || ".join(render(arg, seen)[0] for arg in node.elements), 100

            if isinstance(node, Literal):
                if node.type == LiteralType.EMPTY:
                    return "", 100

                if node.type == LiteralType.STRING:
                    return wrap_field(node.value, SINGLE_QUOTE), 100

                return node.raw_value, 100

            if isinstance(node, Variable):
                if node.name in seen:
                    return get_field_value(node.name), 100

                calculate_expr = self.context.calculate_expressions.get(node.name)
                if calculate_expr is not None:
                    seen.add(node.name)
                    rendered, prec = render(calculate_expr.ast, seen)
                    seen.remove(node.name)
                    return rendered, prec

                return get_field_value(node.name), 100

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

            raise AssertionError(f"Unexpected node type in expression: {type(node)}")

        def render_call(node: Call, seen: set[str]) -> tuple[str, int]:
            rendered_args = [render(arg, seen)[0] for arg in node.args]

            assert isinstance(node.callee, Identifier)

            callee = node.callee.name

            # the parser should already have raised an error for unknown functions
            assert callee in SUPPORTED_FUNCTIONS

            qgis_expr_tmpl = SUPPORTED_FUNCTIONS[callee]

            # the parser should already have raised an error for functions not supported in QGIS
            assert qgis_expr_tmpl.expression

            qgis_expr = qgis_expr_tmpl.format(callee, *rendered_args, ctx=self.context)

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
                # TODO @suricactus: support actual `/` path concatenation operator in XLSForm
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

    def to_qgis(
        self,
        use_current: bool = False,
        expression_type: QgisRenderType = QgisRenderType.EXPRESSION,
    ):
        try:
            return self._to_qgis(
                use_current=use_current, expression_type=expression_type
            )
        except Exception:
            if self.context.skip_expression_errors:
                return ""

            raise

    def is_str(self) -> bool:
        if isinstance(self.ast, Template) and all(
            isinstance(elem, Literal) and elem.type == LiteralType.STRING
            for elem in self.ast.elements
        ):
            return True

        if isinstance(self.ast, Literal) and self.ast.type == LiteralType.STRING:
            return True

        return False
