from __future__ import annotations
from collections.abc import Generator

from dataclasses import dataclass
from enum import StrEnum


class TokenType(StrEnum):
    VARIABLE = "variable"
    IDENT = "ident"
    NUMBER = "number"
    STRING = "string"
    OPERATOR = "operator"
    PUNCTUATION = "punctuation"
    CURRENT = "current"
    EOF = "eof"


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str
    raw_value: str
    start: int
    end: int


OPERATORS: set[str] = {
    "=",
    "!=",
    ">",
    ">=",
    "<",
    "<=",
    "+",
    "-",
    "*",
    "/",
    "and",
    "or",
    "not",
    "div",
    "mod",
}

PUNCTUATION: set[str] = {
    "(",
    ")",
    "[",
    "]",
    "{",
    "}",
    ",",
}


def _is_ident_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_ident_part(ch: str) -> bool:
    return ch.isalnum() or ch in {"_", "-", ":"}


def tokenize(expression: str) -> Generator[Token, None, None]:
    pos: int = 0
    length: int = len(expression)

    while pos < length:
        char: str = expression[pos]

        if char.isspace():
            pos += 1

            continue

        start = pos

        if char == "$" and pos + 1 < length and expression[pos + 1] == "{":
            pos += 2
            var_start = pos

            while pos < length and expression[pos] != "}":
                pos += 1

            if pos >= length:
                raise ValueError("Unterminated variable reference")

            value = expression[var_start:pos]
            pos += 1

            raw_value = expression[start:pos]
            yield Token(TokenType.VARIABLE, value, raw_value, start, pos)

            continue

        if char in {"'", '"'}:
            quote = char
            pos += 1
            literal_start = pos
            escaped = False

            while pos < length:
                curr = expression[pos]

                if escaped:
                    escaped = False
                    pos += 1

                    continue

                if curr == "\\":
                    escaped = True
                    pos += 1

                    continue

                if curr == quote:
                    value = expression[literal_start:pos]
                    pos += 1
                    raw_value = expression[start:pos]
                    yield Token(TokenType.STRING, value, raw_value, start, pos)

                    break

                pos += 1
            else:
                raise ValueError("Unterminated string literal")

            # String literal processed
            continue

        if char == ".":
            if pos + 1 < length and expression[pos + 1].isdigit():
                pos += 1

                while pos < length and expression[pos].isdigit():
                    pos += 1

                raw_value = expression[start:pos]

                yield Token(TokenType.NUMBER, raw_value, raw_value, start, pos)

                continue

            pos += 1
            raw_value = expression[start:pos]

            yield Token(TokenType.CURRENT, ".", raw_value, start, pos)

            continue

        if char.isdigit():
            pos += 1

            while pos < length and expression[pos].isdigit():
                pos += 1

            if (
                pos < length
                and expression[pos] == "."
                and pos + 1 < length
                and expression[pos + 1].isdigit()
            ):
                pos += 1

                while pos < length and expression[pos].isdigit():
                    pos += 1

            raw_value = expression[start:pos]

            yield Token(TokenType.NUMBER, raw_value, raw_value, start, pos)

            continue

        if _is_ident_start(char):
            pos += 1

            while pos < length and _is_ident_part(expression[pos]):
                pos += 1

            value = expression[start:pos]

            if value in OPERATORS:
                token_type = TokenType.OPERATOR
            else:
                token_type = TokenType.IDENT

            raw_value = expression[start:pos]

            yield Token(token_type, value, raw_value, start, pos)

            continue

        if char in PUNCTUATION:
            pos += 1
            raw_value = expression[start:pos]

            yield Token(TokenType.PUNCTUATION, char, raw_value, start, pos)

            continue

        if char in {"!", ">", "<", "=", "+", "-", "*", "/"}:
            pos += 1

            if pos < length and expression[start : pos + 1] in OPERATORS:
                pos += 1

            value = expression[start:pos]

            if value not in OPERATORS:
                raise ValueError(f"Unsupported operator: {value}")

            raw_value = expression[start:pos]
            yield Token(TokenType.OPERATOR, value, raw_value, start, pos)

            continue

        raise ValueError(f"Unexpected character: {char}")

    yield Token(TokenType.EOF, "", "", length, length)
