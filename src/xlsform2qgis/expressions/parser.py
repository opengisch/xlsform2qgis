from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from xlsform2qgis.expressions.registry import SUPPORTED_FUNCTIONS
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
                        raise AssertionError("Mismatched brackets", token.start)

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
                    if token.value in unary_ops:
                        last_significant = token
                        continue
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
        if token.type != token_type:  # pragma: no cover
            raise ParseError("Unexpected token", token.start)

        if value is not None and token.value != value:  # pragma: no cover
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

            raise AssertionError("Unexpected token", token.start)

        if not elements:  # pragma: no cover
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
            if (
                token.value == "-"
                and isinstance(operand, Literal)
                and operand.type == LiteralType.NUMBER
            ):
                return Literal(
                    f"-{operand.value}",
                    f"-{operand.raw_value}",
                    LiteralType.NUMBER,
                )
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

        raise AssertionError("Unexpected token", token.start)

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
                raise AssertionError("Invalid unary expression")

            cls._validate_ast(node.operand)

            return

        if isinstance(node, BinaryOp):
            if node.left is None or node.right is None:
                raise AssertionError("Invalid binary expression")

            cls._validate_ast(node.left)
            cls._validate_ast(node.right)

            return

        if isinstance(node, Call):
            if node.callee is None:
                raise AssertionError("Invalid call expression")

            if not isinstance(node.callee, Identifier):
                raise AssertionError("Invalid call target")

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

        raise AssertionError("Unknown AST node")

    def _validate_call(self, callee_token: Token, args: list[AstNode]) -> None:
        func_name = callee_token.value
        spec = SUPPORTED_FUNCTIONS.get(func_name)

        if spec is None:
            raise ParseError("Unknown function", callee_token.start, callee_token)

        if not spec.validate(len(args)):
            if not callable(spec.expected_args_count):
                expected_args_count = str(spec.expected_args_count)
            else:
                expected_args_count = "callable"

            raise ParseError(
                f"Invalid number of function arguments, expected {expected_args_count}, got {len(args)}",
                callee_token.start,
                callee_token,
            )

        if spec.expression is None:
            # we use `ParseError` here, even though this is not strictly a parsing error,
            raise ParseError(
                "Function not supported in QGIS expressions",
                callee_token.start,
                callee_token,
            )


def parse_expression(expression: str) -> AstNode:
    if not expression.strip():
        return Literal("", "", LiteralType.EMPTY)

    parser = _ExpressionParser.from_expression(expression)
    return parser.parse()


def parse_template(expression: str) -> AstNode:
    if not expression.strip():
        return Literal("", "", LiteralType.EMPTY)

    parser = _ExpressionParser.from_template(expression)

    return parser.parse()
