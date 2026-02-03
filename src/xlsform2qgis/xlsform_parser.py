from __future__ import annotations

from dataclasses import dataclass

from xlsform2qgis.xlsform_tokenizer import Token, TokenType, tokenize


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


def validate_expression(expression: str) -> list[Token]:
    tokens = list(tokenize(expression))
    stack: list[Token] = []
    last_significant: Token | None = None

    for token in tokens:
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
                    raise ParseError("Comma cannot start an expression", token.start)
                if last_significant.type == TokenType.OPERATOR:
                    raise ParseError("Comma after operator", token.start)
                if (
                    last_significant.type == TokenType.PUNCTUATION
                    and last_significant.value in _OPENING
                ):
                    raise ParseError("Comma after opening bracket", token.start)
                last_significant = token
                continue

            last_significant = token
            continue

        if token.type == TokenType.OPERATOR:
            if last_significant is None:
                raise ParseError("Operator cannot start an expression", token.start)
            if last_significant.type == TokenType.OPERATOR:
                raise ParseError("Consecutive operators", token.start)
            if (
                last_significant.type == TokenType.PUNCTUATION
                and last_significant.value in _OPENING
            ):
                raise ParseError("Operator after opening bracket", token.start)
            if (
                last_significant.type == TokenType.PUNCTUATION
                and last_significant.value == ","
            ):
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

    return tokens
