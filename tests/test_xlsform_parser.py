import pytest

from xlsform2qgis.xlsform_parser import (
    BinaryOp,
    BracketList,
    Call,
    Identifier,
    Literal,
    ParseError,
    UnaryOp,
    Variable,
    parse_expression,
    validate_expression,
)


class TestXlsformParserBrackets:
    def test_balanced_parentheses(self):
        validate_expression("(${a} + 1) * (2 + 3)")

    def test_balanced_brackets(self):
        validate_expression("[1, 2, 3]")

    def test_balanced_braces(self):
        validate_expression("{1, 2}")

    def test_unmatched_closing(self):
        with pytest.raises(ParseError, match="Unmatched closing bracket"):
            validate_expression("1 + 2)")

    def test_unclosed_opening(self):
        with pytest.raises(ParseError, match="Unclosed bracket"):
            validate_expression("(1 + 2")

    def test_mismatched_brackets(self):
        with pytest.raises(ParseError, match="Mismatched brackets"):
            validate_expression("(]")


class TestXlsformParserCommas:
    def test_comma_separated_list(self):
        validate_expression("(1, 2, 3)")

    def test_no_trailing_comma(self):
        with pytest.raises(ParseError, match="Trailing comma"):
            validate_expression("(1, 2,)")

    def test_no_leading_comma(self):
        with pytest.raises(ParseError, match="Comma cannot start an expression"):
            validate_expression(", 1")

    def test_no_comma_after_opening(self):
        with pytest.raises(ParseError, match="Comma after opening bracket"):
            validate_expression("(, 1)")


class TestXlsformParserOperators:
    def test_operator_between_operands(self):
        validate_expression("${a} + ${b} - 3")

    def test_no_consecutive_operators(self):
        with pytest.raises(ParseError, match="Consecutive operators"):
            validate_expression("1 + * 2")

    def test_no_trailing_operator(self):
        with pytest.raises(ParseError, match="Trailing operator"):
            validate_expression("1 +")

    def test_no_operator_at_start(self):
        validate_expression("+ 1")
        with pytest.raises(ParseError, match="Operator cannot start an expression"):
            validate_expression("/ 1")

    def test_no_operator_after_opening(self):
        validate_expression("(+ 1)")

        with pytest.raises(ParseError, match="Operator after opening bracket"):
            validate_expression("(/ 1)")

    def test_no_operator_after_comma(self):
        validate_expression("(1, +2)")

        with pytest.raises(ParseError, match="Operator after comma"):
            validate_expression("(1, /2)")


class TestXlsformParserAst:
    def test_binary_expression_ast(self):
        ast = parse_expression("${a} + 2")
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "+"
        assert isinstance(ast.left, Variable)
        assert ast.left.name == "a"
        assert isinstance(ast.right, Literal)
        assert ast.right.value == "2"

    def test_unary_expression_ast(self):
        ast = parse_expression("not ${flag}")
        assert isinstance(ast, UnaryOp)
        assert ast.operator == "not"
        assert isinstance(ast.operand, Variable)
        assert ast.operand.name == "flag"

    def test_function_call_ast(self):
        ast = parse_expression("regex(${field}, '^[0-9]+$')")
        assert isinstance(ast, Call)
        assert isinstance(ast.callee, Identifier)
        assert ast.callee.name == "regex"
        assert len(ast.args) == 2
        assert isinstance(ast.args[0], Variable)
        assert isinstance(ast.args[1], Literal)

    def test_list_literal_ast(self):
        ast = parse_expression("[1, 2, 3]")
        assert isinstance(ast, BracketList)
        assert ast.open_bracket == "["
        assert len(ast.elements) == 3
