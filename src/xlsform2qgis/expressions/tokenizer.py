from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re


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
    # math operators, see https://docs.getodk.org/form-operators-functions/#math-operators
    "+",
    "-",
    "*",
    "div",
    "mod",
    # comparison operators, see https://docs.getodk.org/form-operators-functions/#comparison-operators
    "=",
    "!=",
    ">",
    ">=",
    "<",
    "<=",
    # boolean operators, see https://docs.getodk.org/form-operators-functions/#boolean-operators
    "and",
    "or",
}

PUNCTUATION: set[str] = {
    "(",
    ")",
    ",",
}


LEXICON: tuple[tuple[TokenType, re.Pattern[str]], ...] = (
    (TokenType.STRING, re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"")),
    (TokenType.VARIABLE, re.compile(r"\$\{[^}]*\}")),
    (TokenType.NUMBER, re.compile(r"\d+(?:\.\d+)?|\.\d+")),
    (TokenType.CURRENT, re.compile(r"\.")),
    (TokenType.OPERATOR, re.compile(r"!=|>=|<=|=|>|<|\+|-|\*")),
    (TokenType.OPERATOR, re.compile(r"\b(?:and|or|div|mod)\b")),
    (TokenType.PUNCTUATION, re.compile(r"[\(\),]")),
    (TokenType.IDENT, re.compile(r"[A-Za-z_][A-Za-z0-9_\-:]*")),
)


_WHITESPACE = re.compile(r"\s+")


def _normalize_value(token_type: TokenType, raw_value: str) -> str:
    if token_type == TokenType.VARIABLE:
        return raw_value[2:-1]
    if token_type == TokenType.STRING:
        return raw_value[1:-1]
    if token_type == TokenType.CURRENT:
        return "."
    return raw_value


def tokenize(expression: str) -> list[Token]:
    tokens: list[Token] = []
    pos: int = 0
    length: int = len(expression)

    while pos < length:
        whitespace_match = _WHITESPACE.match(expression, pos)
        if whitespace_match:
            pos = whitespace_match.end()
            continue

        best_type: TokenType | None = None
        best_match: re.Match[str] | None = None

        for token_type, pattern in LEXICON:
            match = pattern.match(expression, pos)
            if not match:
                continue

            if best_match is None or match.end() > best_match.end():
                best_match = match
                best_type = token_type

        if best_match is None or best_type is None:
            raise ValueError(f"Unexpected character: {expression[pos]}")

        start = pos
        end = best_match.end()
        raw_value = expression[start:end]

        if best_type == TokenType.OPERATOR and raw_value not in OPERATORS:
            raise ValueError(f"Unsupported operator: {raw_value}")

        value = _normalize_value(best_type, raw_value)
        tokens.append(Token(best_type, value, raw_value, start, end))
        pos = end

    tokens.append(Token(TokenType.EOF, "", "", length, length))
    return tokens
