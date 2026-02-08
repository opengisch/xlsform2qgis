from __future__ import annotations

from collections.abc import Callable

from dataclasses import dataclass
from enum import StrEnum

from xlsform2qgis.expressions.tokenizer import (
    Token,
    TokenType,
    tokenize_expression,
    tokenize_template,
)


class AstNode:
    pass


class LiteralType(StrEnum):
    NUMBER = "number"
    STRING = "string"
    EMPTY = "empty"

    @staticmethod
    def from_token_type(token_type: TokenType) -> "LiteralType":
        if token_type == TokenType.NUMBER:
            return LiteralType.NUMBER
        if token_type == TokenType.STRING:
            return LiteralType.STRING

        raise ValueError(f"Cannot convert token type {token_type} to LiteralType")


class ParserType(StrEnum):
    EXPRESSION = "expression"
    TEMPLATE = "template"


@dataclass(frozen=True)
class Literal(AstNode):
    value: str
    raw_value: str
    type: LiteralType


@dataclass(frozen=True)
class Variable(AstNode):
    name: str
    raw_value: str


@dataclass(frozen=True)
class Identifier(AstNode):
    name: str
    raw_value: str


@dataclass(frozen=True)
class Current(AstNode):
    raw_value: str


@dataclass(frozen=True)
class UnaryOp(AstNode):
    operator: str
    operand: AstNode


@dataclass(frozen=True)
class BinaryOp(AstNode):
    operator: str
    left: AstNode
    right: AstNode


@dataclass(frozen=True)
class Call(AstNode):
    callee: AstNode
    args: list[AstNode]


@dataclass(frozen=True)
class BracketList(AstNode):
    open_bracket: str
    close_bracket: str
    elements: list[AstNode]


@dataclass(frozen=True)
class Template(AstNode):
    elements: list[AstNode]


class ParseError(Exception):
    message: str
    position: int | None = None
    token: Token | None = None

    def __init__(
        self, message: str, position: int | None = None, token: Token | None = None
    ) -> None:
        self.message = message
        self.position = position
        self.token = token

        super().__init__(self.__str__())

    def __str__(self) -> str:
        msg = self.message

        if self.token:
            msg += f" `{self.token.raw_value}`"

        if self.position is not None:
            msg += f" at position {self.position}"

        return msg


class FunctionSpec:
    expression: str | None

    _validate_function: Callable[[int], bool]

    def __init__(
        self,
        args_count: Callable | int | tuple[int, int | None],
        qgis_expression: str | None,
    ) -> None:
        if callable(args_count):
            self._validate_function = args_count
        elif isinstance(args_count, tuple):
            min_args, max_args = args_count
            self._validate_function = lambda c: self._validate_arg_count(
                c, min_args, max_args
            )
        elif isinstance(args_count, int):
            min_args, max_args = args_count, args_count
            self._validate_function = lambda c: self._validate_arg_count(
                c, min_args, max_args
            )
        else:
            raise ValueError(
                f"Invalid argument for `FunctionSpec`, expected int, tuple[int, int], or callable, got {type(args_count)}"
            )

        self.expression = qgis_expression

    def _validate_arg_count(
        self, count: int, min_args: int, max_args: int | None
    ) -> bool:
        if count < min_args:
            return False

        if max_args is not None and count > max_args:
            return False

        return True

    def validate(self, count: int) -> bool:
        return self._validate_function(count)


SUPPORTED_FUNCTIONS: dict[str, FunctionSpec] = {
    "if": FunctionSpec(3, "if({1}, {2}, {3})"),
    "position": FunctionSpec(1, None),
    "once": FunctionSpec(1, None),
    "selected": FunctionSpec(
        2,
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
    """.strip(),
    ),
    "selected-at": FunctionSpec(2, "coalesce(array_get({1}, {2}), '')"),
    "count-selected": FunctionSpec(1, "array_length({1})"),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#jr-choice-name
    "jr:choice-name": FunctionSpec(2, None),
    "indexed-repeat": FunctionSpec(lambda c: c in {3, 5, 7}, None),
    "count": FunctionSpec(1, "array_length({1})"),
    "count-non-empty": FunctionSpec(1, "array_length({1}) - count_missing({1})"),
    "sum": FunctionSpec(1, "array_sum({1})"),
    "max": FunctionSpec(1, "array_max({1})"),
    "min": FunctionSpec(1, "array_min({1})"),
    "regex": FunctionSpec(2, "regexp_match({1}, {2})"),
    "contains": FunctionSpec(2, "strpos({1}, {2}) > 0"),
    "starts-with": FunctionSpec(2, "left({1}, length({2})) = {2}"),
    "ends-with": FunctionSpec(2, "right({1}, length({2})) = {2}"),
    "substr": FunctionSpec((2, 3), "substr({1}, {2} + 1, {3})"),
    "substring-before": FunctionSpec(2, "substr({1}, 1, strpos({1}, {2}))"),
    "substring-after": FunctionSpec(2, "substr({1}, strpos({1}, {2}) + 1)"),
    "translate": FunctionSpec(
        3,
        "array_foreach(string_to_array({2}, ''), replace({1}, @element, coalesce(array_get(string_to_array({2}, ''), @counter), '')))",
    ),
    "string-length": FunctionSpec((0, 1), "length({1})"),
    "normalize-space": FunctionSpec(1, "trim( regexp_replace( {1}, '\\s+', ' ') )"),
    "concat": FunctionSpec((1, None), "concat({1}, {2})"),
    "join": FunctionSpec(2, "array_to_string({1}, {2})"),
    "boolean-from-string": FunctionSpec(1, "{1} == 'true' or {1} == '1'"),
    "string": FunctionSpec(1, "to_string({1})"),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#digest
    "digest": FunctionSpec((2, 3), None),
    "base64-decode": FunctionSpec(1, "from_base64({1})"),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#extract-signed
    "extract-signed": FunctionSpec(2, None),
    "round": FunctionSpec(2, "round({1}, {2})"),
    "int": FunctionSpec(1, "to_int({1})"),
    "number": FunctionSpec(1, "to_real({1})"),
    "pow": FunctionSpec(2, "{1} ^ {2}"),
    "log": FunctionSpec(1, "ln({1})"),
    "log10": FunctionSpec(1, "log({1})"),
    "abs": FunctionSpec(1, "abs({1})"),
    "sin": FunctionSpec(1, "sin({1})"),
    "cos": FunctionSpec(1, "cos({1})"),
    "tan": FunctionSpec(1, "tan({1})"),
    "asin": FunctionSpec(1, "asin({1})"),
    "acos": FunctionSpec(1, "acos({1})"),
    "atan": FunctionSpec(1, "atan({1})"),
    "atan2": FunctionSpec(2, "atan2({1}, {2})"),
    "sqrt": FunctionSpec(1, "sqrt({1})"),
    "exp": FunctionSpec(1, "exp({1})"),
    "exp10": FunctionSpec(1, "10 ^ {1}"),
    "pi": FunctionSpec(0, "pi()"),
    "today": FunctionSpec(0, "format_date(now(), 'yyyy-MM-dd')"),
    "now": FunctionSpec(0, "now()"),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#converting-dates-and-time
    "decimal-date-time": FunctionSpec(1, None),
    "date": FunctionSpec(1, None),
    "decimal-time": FunctionSpec(1, None),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#format-date
    "format-date": FunctionSpec(2, None),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#format-date-time
    "format-date-time": FunctionSpec(2, None),
    "area": FunctionSpec(1, "area({1})"),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#distance
    "distance": FunctionSpec((1, None), None),
    "geofence": FunctionSpec(2, "contains({2}, {1})"),
    "random": FunctionSpec(0, "randf()"),
    "randomize": FunctionSpec((1, 2), "array_get({1}, rand(0, array_length({1}) - 1))"),
    "uuid": FunctionSpec(
        (0, 1),
        "if({1}, substr(repeat( uuid(format:='WithoutBraces'), ceil({1} / 32) ), 1, {1}), uuid(format:='WithoutBraces'))",
    ),
    "boolean": FunctionSpec(1, "to_bool({1})"),
    "not": FunctionSpec(1, "not {1}"),
    "coalesce": FunctionSpec(2, "coalesce({1}, {2})"),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#checklist
    "checklist": FunctionSpec((3, None), None),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#weighted-checklist
    "weighted-checklist": FunctionSpec(lambda c: c >= 4 and (c - 2) % 2 == 0, None),
    "true": FunctionSpec(0, "true"),
    "false": FunctionSpec(0, "false"),
    # TODO @suricactus: implement https://xlsform.org/en/#how-to-pull-data-from-csv
    "pulldata": FunctionSpec(4, None),
}
"""Mapping of supported xlsform function names and the expected number of arguments as well as their QGIS expression equivalents."""


OPENING_BRACKET = "("
CLOSING_BRACKET = ")"


class _ExpressionParser:
    def __init__(self, tokens: list[Token], parser_type: ParserType) -> None:
        self._tokens = tokens
        self._pos = 0
        self._parser_type = parser_type

    @classmethod
    def from_expression(cls, expression: str) -> "_ExpressionParser":
        tokens = list(tokenize_expression(expression))
        cls._validate_tokens(tokens)
        return cls(tokens, parser_type=ParserType.EXPRESSION)

    @classmethod
    def from_template(cls, expression: str) -> "_ExpressionParser":
        tokens = list(tokenize_template(expression))
        cls._validate_tokens(tokens)
        return cls(tokens, parser_type=ParserType.TEMPLATE)

    @staticmethod
    def _validate_tokens(tokens: list[Token]) -> None:
        stack: list[Token] = []
        last_significant: Token | None = None
        total = len(tokens)
        unary_ops = {"+", "-"}

        for index, token in enumerate(tokens):
            if token.type == TokenType.EOF:
                break

            if token.type == TokenType.PUNCTUATION:
                value = token.value
                if value == OPENING_BRACKET:
                    stack.append(token)
                    last_significant = token
                    continue

                if value in CLOSING_BRACKET:
                    if not stack:
                        raise ParseError("Unmatched closing bracket", token.start)

                    opening = stack.pop()
                    if opening.value != OPENING_BRACKET:
                        raise ParseError("Mismatched brackets", token.start)

                    last_significant = token
                    continue

                if value == ",":
                    if last_significant is None:
                        raise ParseError(
                            "Comma cannot start an expression", token.start
                        )
                    if last_significant.type == TokenType.OPERATOR:
                        raise ParseError("Comma after operator", token.start)
                    if (
                        last_significant.type == TokenType.PUNCTUATION
                        and last_significant.value == OPENING_BRACKET
                    ):
                        raise ParseError("Comma after opening bracket", token.start)
                    if index + 1 < total:
                        next_token = tokens[index + 1]
                        if (
                            next_token.type == TokenType.PUNCTUATION
                            and next_token.value == CLOSING_BRACKET
                        ):
                            raise ParseError("Trailing comma", token.start)
                        if next_token.type == TokenType.EOF:
                            raise ParseError("Trailing comma", token.start)
                    last_significant = token
                    continue

                last_significant = token
                continue

            if token.type == TokenType.OPERATOR:
                if last_significant is None:
                    if token.value in unary_ops:
                        last_significant = token
                        continue
                    raise ParseError("Operator cannot start an expression", token.start)
                if last_significant.type == TokenType.OPERATOR:
                    raise ParseError("Consecutive operators", token.start)
                if (
                    last_significant.type == TokenType.PUNCTUATION
                    and last_significant.value == OPENING_BRACKET
                ):
                    if token.value in unary_ops:
                        last_significant = token
                        continue
                    raise ParseError("Operator after opening bracket", token.start)
                if (
                    last_significant.type == TokenType.PUNCTUATION
                    and last_significant.value == ","
                ):
                    if token.value in unary_ops:
                        last_significant = token
                        continue
                    raise ParseError("Operator after comma", token.start)
                last_significant = token
                continue

            last_significant = token

        if stack:
            raise ParseError("Unclosed bracket", stack[-1].start)

        if last_significant is not None:
            if last_significant.type == TokenType.OPERATOR:
                raise ParseError("Trailing operator", last_significant.start)
            if (
                last_significant.type == TokenType.PUNCTUATION
                and last_significant.value == ","
            ):
                raise ParseError("Trailing comma", last_significant.start)

    def _current(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        token = self._current()
        if token.type != TokenType.EOF:
            self._pos += 1
        return token

    def _match(self, token_type: TokenType, value: str | None = None) -> bool:
        token = self._current()
        if token.type != token_type:
            return False
        if value is not None and token.value != value:
            return False
        self._advance()
        return True

    def _expect(self, token_type: TokenType, value: str | None = None) -> Token:
        token = self._current()
        if token.type != token_type:
            raise ParseError("Unexpected token", token.start)
        if value is not None and token.value != value:
            raise ParseError("Unexpected token", token.start)
        self._advance()
        return token

    def parse(self) -> AstNode:
        if self._parser_type == ParserType.TEMPLATE:
            return self._parse_template()
        else:
            return self._parse_expression()

    def _parse_expression(self) -> AstNode:
        expr = self._parse_or()
        if self._current().type != TokenType.EOF:
            raise ParseError("Unexpected token", self._current().start)
        self._validate_ast(expr)
        return expr

    def _parse_template(self) -> AstNode:
        elements: list[AstNode] = []
        while self._current().type != TokenType.EOF:
            token = self._current()

            if token.type == TokenType.STRING:
                elements.append(
                    Literal(token.value, token.raw_value, LiteralType.STRING)
                )
                self._advance()

                continue

            if token.type == TokenType.VARIABLE:
                elements.append(Variable(token.value, token.raw_value))
                self._advance()

                continue

            raise ParseError("Unexpected token", token.start)

        if not elements:
            return Literal("", "", LiteralType.EMPTY)

        return Template(elements)

    def _parse_or(self) -> AstNode:
        left = self._parse_and()
        while self._match(TokenType.OPERATOR, "or"):
            right = self._parse_and()
            left = BinaryOp("or", left, right)
        return left

    def _parse_and(self) -> AstNode:
        left = self._parse_comparison()
        while self._match(TokenType.OPERATOR, "and"):
            right = self._parse_comparison()
            left = BinaryOp("and", left, right)
        return left

    def _parse_comparison(self) -> AstNode:
        left = self._parse_additive()
        while True:
            token = self._current()
            if token.type != TokenType.OPERATOR:
                break
            if token.value not in {"=", "!=", ">", ">=", "<", "<="}:
                break
            self._advance()
            right = self._parse_additive()
            left = BinaryOp(token.value, left, right)
        return left

    def _parse_additive(self) -> AstNode:
        left = self._parse_multiplicative()
        while True:
            token = self._current()
            if token.type != TokenType.OPERATOR:
                break
            if token.value not in {"+", "-"}:
                break
            self._advance()
            right = self._parse_multiplicative()
            left = BinaryOp(token.value, left, right)
        return left

    def _parse_multiplicative(self) -> AstNode:
        left = self._parse_unary()
        while True:
            token = self._current()
            if token.type != TokenType.OPERATOR:
                break
            if token.value not in {"*", "/", "div", "mod"}:
                break
            self._advance()
            right = self._parse_unary()
            left = BinaryOp(token.value, left, right)
        return left

    def _parse_unary(self) -> AstNode:
        token = self._current()
        if token.type == TokenType.OPERATOR and token.value in {"not", "+", "-"}:
            self._advance()
            operand = self._parse_unary()
            return UnaryOp(token.value, operand)
        return self._parse_primary()

    def _parse_primary(self) -> AstNode:
        token = self._current()
        if token.type == TokenType.NUMBER or token.type == TokenType.STRING:
            self._advance()
            return Literal(
                token.value, token.raw_value, LiteralType.from_token_type(token.type)
            )
        if token.type == TokenType.VARIABLE:
            self._advance()
            return Variable(token.value, token.raw_value)
        if token.type == TokenType.CURRENT:
            self._advance()
            return Current(token.raw_value)
        if token.type == TokenType.IDENT:
            self._advance()
            node: AstNode = Identifier(token.value, token.raw_value)
            if self._match(TokenType.PUNCTUATION, OPENING_BRACKET):
                args = self._parse_arguments(CLOSING_BRACKET)
                self._validate_call(token, args)
                node = Call(node, args)
            return node
        if token.type == TokenType.PUNCTUATION and token.value == OPENING_BRACKET:
            self._advance()
            open_bracket = token.value
            close_bracket = CLOSING_BRACKET
            elements = self._parse_arguments(close_bracket)
            if open_bracket == OPENING_BRACKET and len(elements) == 1:
                return elements[0]
            return BracketList(open_bracket, close_bracket, elements)
        raise ParseError("Unexpected token", token.start)

    def _parse_arguments(self, close_bracket: str) -> list[AstNode]:
        elements: list[AstNode] = []
        if self._match(TokenType.PUNCTUATION, close_bracket):
            return elements
        while True:
            elements.append(self._parse_or())
            if self._match(TokenType.PUNCTUATION, close_bracket):
                break
            comma = self._expect(TokenType.PUNCTUATION, ",")
            if (
                self._current().type == TokenType.PUNCTUATION
                and self._current().value == close_bracket
            ):
                raise ParseError("Trailing comma", comma.start)
        return elements

    @classmethod
    def _validate_ast(cls, node: AstNode) -> None:
        if isinstance(node, UnaryOp):
            if node.operand is None:
                raise ParseError("Invalid unary expression")
            cls._validate_ast(node.operand)
            return
        if isinstance(node, BinaryOp):
            if node.left is None or node.right is None:
                raise ParseError("Invalid binary expression")
            cls._validate_ast(node.left)
            cls._validate_ast(node.right)
            return
        if isinstance(node, Call):
            if node.callee is None:
                raise ParseError("Invalid call expression")
            if not isinstance(node.callee, Identifier):
                raise ParseError("Invalid call target")
            cls._validate_ast(node.callee)
            for arg in node.args:
                cls._validate_ast(arg)
            return
        if isinstance(node, BracketList):
            for element in node.elements:
                cls._validate_ast(element)
            return
        if isinstance(node, (Literal, Variable, Identifier, Current)):
            return
        raise ParseError("Unknown AST node")

    def _validate_call(self, callee_token: Token, args: list[AstNode]) -> None:
        func_name = callee_token.value
        spec = SUPPORTED_FUNCTIONS.get(func_name)

        if spec is None:
            raise ParseError("Unknown function", callee_token.start, callee_token)

        if not spec.validate(len(args)):
            raise ParseError(
                "Invalid number of function arguments", callee_token.start, callee_token
            )


def parse_expression(expression: str) -> AstNode:
    if not expression.strip():
        return Literal("", "", LiteralType.EMPTY)

    parser = _ExpressionParser.from_expression(expression)
    return parser._parse_expression()


def parse_template(expression: str) -> AstNode:
    if not expression.strip():
        return Literal("", "", LiteralType.EMPTY)

    parser = _ExpressionParser.from_template(expression)

    return parser._parse_template()
