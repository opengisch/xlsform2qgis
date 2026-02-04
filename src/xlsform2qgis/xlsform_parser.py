from __future__ import annotations

from dataclasses import dataclass

from xlsform2qgis.xlsform_tokenizer import Token, TokenType, tokenize


class AstNode:
    pass


@dataclass(frozen=True)
class Literal(AstNode):
    value: str
    raw_value: str
    token_type: TokenType


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
class ParseError(Exception):
    message: str
    position: int | None = None

    def __str__(self) -> str:
        if self.position is None:
            return self.message
        return f"{self.message} at position {self.position}"


_OPENING = {"(": ")", "[": "]", "{": "}"}
_CLOSING = {")": "(", "]": "[", "}": "{"}


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
        unary_ops = {"not", "+", "-"}

        for index, token in enumerate(tokens):
            if token.type == TokenType.EOF:
                break

            if token.type == TokenType.PUNCTUATION:
                value = token.value
                if value in _OPENING:
                    stack.append(token)
                    last_significant = token
                    continue

                if value in _CLOSING:
                    if not stack:
                        raise ParseError("Unmatched closing bracket", token.start)
                    opening = stack.pop()
                    if _OPENING[opening.value] != value:
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
                        and last_significant.value in _OPENING
                    ):
                        raise ParseError("Comma after opening bracket", token.start)
                    if index + 1 < total:
                        next_token = tokens[index + 1]
                        if (
                            next_token.type == TokenType.PUNCTUATION
                            and next_token.value in _CLOSING
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
                    and last_significant.value in _OPENING
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
            return Literal(token.value, token.raw_value, token.type)
        if token.type == TokenType.VARIABLE:
            self._advance()
            return Variable(token.value, token.raw_value)
        if token.type == TokenType.CURRENT:
            self._advance()
            return Current(token.raw_value)
        if token.type == TokenType.IDENT:
            self._advance()
            node: AstNode = Identifier(token.value, token.raw_value)
            if self._match(TokenType.PUNCTUATION, "("):
                args = self._parse_arguments(")")
                node = Call(node, args)
            return node
        if token.type == TokenType.PUNCTUATION and token.value in {"(", "[", "{"}:
            self._advance()
            open_bracket = token.value
            close_bracket = _OPENING[open_bracket]
            elements = self._parse_arguments(close_bracket)
            if open_bracket == "(" and len(elements) == 1:
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


def parse_expression(expression: str) -> AstNode:
    parser = _Parser.from_expression(expression)
    return parser.parse()
