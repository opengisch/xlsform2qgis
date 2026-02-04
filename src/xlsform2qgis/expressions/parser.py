from __future__ import annotations

from collections.abc import Callable

from dataclasses import dataclass
from enum import StrEnum

from xlsform2qgis.expressions.tokenizer import Token, TokenType, tokenize


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
    _validate_function: Callable[[int], bool]

    def __init__(
        self, min_args_or_callable: Callable | int, max_args: int | None = None
    ) -> None:
        if callable(min_args_or_callable):
            self._validate_function = min_args_or_callable
        else:
            self._validate_function = lambda c: self._validate_arg_count(
                c, min_args_or_callable, max_args
            )

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
    "if": FunctionSpec(3, 3),
    "position": FunctionSpec(1, 1),
    "once": FunctionSpec(1, 1),
    "selected": FunctionSpec(2, 2),
    "selected-at": FunctionSpec(2, 2),
    "count-selected": FunctionSpec(1, 1),
    "jr:choice-name": FunctionSpec(2, 2),
    "indexed-repeat": FunctionSpec(lambda c: c in {3, 5, 7}),
    "count": FunctionSpec(1, 1),
    "count-non-empty": FunctionSpec(1, 1),
    "sum": FunctionSpec(1, 1),
    "max": FunctionSpec(1, 1),
    "min": FunctionSpec(1, 1),
    "regex": FunctionSpec(2, 2),
    "contains": FunctionSpec(2, 2),
    "starts-with": FunctionSpec(2, 2),
    "ends-with": FunctionSpec(2, 2),
    "substr": FunctionSpec(2, 3),
    "substring-before": FunctionSpec(2, 2),
    "substring-after": FunctionSpec(2, 2),
    "translate": FunctionSpec(3, 3),
    "string-length": FunctionSpec(0, 1),
    "normalize-space": FunctionSpec(1, 1),
    "concat": FunctionSpec(1, None),
    "join": FunctionSpec(2, 2),
    "boolean-from-string": FunctionSpec(1, 1),
    "string": FunctionSpec(1, 1),
    "digest": FunctionSpec(2, 3),
    "base64-decode": FunctionSpec(1, 1),
    "extract-signed": FunctionSpec(2, 2),
    "round": FunctionSpec(2, 2),
    "int": FunctionSpec(1, 1),
    "number": FunctionSpec(1, 1),
    "pow": FunctionSpec(2, 2),
    "log": FunctionSpec(1, 1),
    "log10": FunctionSpec(1, 1),
    "abs": FunctionSpec(1, 1),
    "sin": FunctionSpec(1, 1),
    "cos": FunctionSpec(1, 1),
    "tan": FunctionSpec(1, 1),
    "asin": FunctionSpec(1, 1),
    "acos": FunctionSpec(1, 1),
    "atan": FunctionSpec(1, 1),
    "atan2": FunctionSpec(2, 2),
    "sqrt": FunctionSpec(1, 1),
    "exp": FunctionSpec(1, 1),
    "exp10": FunctionSpec(1, 1),
    "pi": FunctionSpec(0, 0),
    "today": FunctionSpec(0, 0),
    "now": FunctionSpec(0, 0),
    "decimal-date-time": FunctionSpec(1, 1),
    "date": FunctionSpec(1, 1),
    "decimal-time": FunctionSpec(1, 1),
    "format-date": FunctionSpec(2, 2),
    "format-date-time": FunctionSpec(2, 2),
    "area": FunctionSpec(1, 1),
    "distance": FunctionSpec(1, None),
    "geofence": FunctionSpec(2, 2),
    "random": FunctionSpec(0, 0),
    "randomize": FunctionSpec(1, 2),
    "uuid": FunctionSpec(0, 1),
    "boolean": FunctionSpec(1, 1),
    "not": FunctionSpec(1, 1),
    "coalesce": FunctionSpec(2, 2),
    "checklist": FunctionSpec(3, None),
    "weighted-checklist": FunctionSpec(lambda c: c >= 4 and (c - 2) % 2 == 0),
    "true": FunctionSpec(0, 0),
    "false": FunctionSpec(0, 0),
}

OPENING_BRACKET = "("
CLOSING_BRACKET = ")"


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    @classmethod
    def from_expression(cls, expression: str) -> "_Parser":
        tokens = list(tokenize(expression))
        cls._validate_tokens(tokens)
        return cls(tokens)

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
        expr = self._parse_or()
        if self._current().type != TokenType.EOF:
            raise ParseError("Unexpected token", self._current().start)
        self._validate_ast(expr)
        return expr

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

    parser = _Parser.from_expression(expression)
    return parser.parse()
