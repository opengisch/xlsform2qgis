from dataclasses import dataclass

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
    parse_expression,
)


@dataclass
class ExpressionContext:
    calculate_expressions: dict[str, "Expression"]
    current_field: str


class Expression:
    def __init__(self, expression_str: str, context: ExpressionContext):
        self.expression_str = expression_str
        self.ast = parse_expression(expression_str)
        self.context = context

    def to_qgis_expression(self) -> str:
        def wrap_field(field_name: str) -> str:
            return f'"{field_name}"'

        def render(node: AstNode, seen: set[str]) -> tuple[str, int]:
            if isinstance(node, Literal):
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
                prec = _binary_precedence(node.operator)

                if left_prec < prec:
                    left = f"({left})"
                if right_prec < prec or (
                    right_prec == prec and node.operator in _non_associative_ops()
                ):
                    right = f"({right})"

                return f"{left} {node.operator} {right}", prec

            if isinstance(node, Call):
                return render_call(node, seen)

            if isinstance(node, BracketList):
                elements = [render(arg, seen)[0] for arg in node.elements]
                joined = ", ".join(elements)
                return f"{node.open_bracket}{joined}{node.close_bracket}", 100

            return "", 100

        def render_call(node: Call, seen: set[str]) -> tuple[str, int]:
            if isinstance(node.callee, Identifier):
                name = node.callee.name
                args = [render(arg, seen)[0] for arg in node.args]

                if name == "selected" and len(args) == 2:
                    return f"{args[0]} = {args[1]}", 50

                if name == "regex" and len(args) == 2:
                    return f"regexp_match({args[0]}, {args[1]})", 100

                if name == "string-length" and len(args) == 1:
                    return f"length( {args[0]} )", 100

                if name == "today" and len(args) == 0:
                    return "format_date(now(),'yyyy-MM-dd')", 100

                if name in {"true", "false"} and len(args) == 0:
                    return name, 100

                return f"{name}({', '.join(args)})", 100

            callee, _ = render(node.callee, seen)
            rendered_args = ", ".join(render(arg, seen)[0] for arg in node.args)

            return f"{callee}({rendered_args})", 100

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

        return render(self.ast, set())[0]
