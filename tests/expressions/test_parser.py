import pytest

from xlsform2qgis.expressions.parser import (
    BinaryOp,
    BracketList,
    Call,
    Identifier,
    Literal,
    LiteralType,
    ParseError,
    Template,
    UnaryOp,
    Variable,
    parse_expression,
    parse_template,
)


class TestXlsformParser:
    def test_balanced_parentheses(self):
        ast = parse_expression("(${a} + 1) * (2 + 3)")
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "*"
        assert isinstance(ast.left, BinaryOp)
        assert ast.left.operator == "+"
        assert isinstance(ast.left.left, Variable)
        assert ast.left.left.name == "a"
        assert isinstance(ast.left.right, Literal)
        assert ast.left.right.value == "1"
        assert isinstance(ast.right, BinaryOp)
        assert ast.right.operator == "+"
        assert isinstance(ast.right.left, Literal)
        assert ast.right.left.value == "2"
        assert isinstance(ast.right.right, Literal)
        assert ast.right.right.value == "3"

    def test_balanced_brackets(self):
        ast = parse_expression("(1, 2, 3)")
        assert isinstance(ast, BracketList)
        assert ast.open_bracket == "("
        assert ast.close_bracket == ")"
        assert len(ast.elements) == 3
        assert isinstance(ast.elements[0], Literal)
        assert ast.elements[0].value == "1"
        assert isinstance(ast.elements[1], Literal)
        assert ast.elements[1].value == "2"
        assert isinstance(ast.elements[2], Literal)
        assert ast.elements[2].value == "3"

    def test_comma_separated_list(self):
        ast = parse_expression("(1, 2, 3)")
        assert isinstance(ast, BracketList)
        assert ast.open_bracket == "("
        assert ast.close_bracket == ")"
        assert len(ast.elements) == 3
        assert isinstance(ast.elements[0], Literal)
        assert ast.elements[0].value == "1"
        assert isinstance(ast.elements[1], Literal)
        assert ast.elements[1].value == "2"
        assert isinstance(ast.elements[2], Literal)
        assert ast.elements[2].value == "3"

    def test_unmatched_closing(self):
        with pytest.raises(ParseError, match="Unmatched closing bracket"):
            parse_expression("1 + 2)")

    def test_unclosed_opening(self):
        with pytest.raises(ParseError, match="Unclosed bracket"):
            parse_expression("(1 + 2")

    def test_no_trailing_comma(self):
        with pytest.raises(ParseError, match="Trailing comma"):
            parse_expression("(1, 2,)")

    def test_no_leading_comma(self):
        with pytest.raises(ParseError, match="Comma cannot start an expression"):
            parse_expression(", 1")

    def test_no_comma_after_opening(self):
        with pytest.raises(ParseError, match="Comma after opening bracket"):
            parse_expression("(, 1)")

    def test_operator_between_operands(self):
        ast = parse_expression("${a} + ${b} - 3")
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "-"
        assert isinstance(ast.left, BinaryOp)
        assert ast.left.operator == "+"
        assert isinstance(ast.right, Literal)
        assert ast.right.value == "3"

    def test_no_consecutive_operators(self):
        with pytest.raises(ParseError, match="Consecutive operators"):
            parse_expression("1 + * 2")

    def test_no_trailing_operator(self):
        with pytest.raises(ParseError, match="Trailing operator"):
            parse_expression("1 +")

    def test_unary_operator_at_start(self):
        ast = parse_expression("+ 1")
        assert isinstance(ast, UnaryOp)
        assert ast.operator == "+"
        assert isinstance(ast.operand, Literal)
        assert ast.operand.value == "1"

    def test_no_operator_at_start(self):
        with pytest.raises(ParseError, match="Operator cannot start an expression"):
            parse_expression("* 1")

    def test_unary_operator_after_opening(self):
        ast = parse_expression("(+ 1)")
        assert isinstance(ast, UnaryOp)
        assert ast.operator == "+"
        assert isinstance(ast.operand, Literal)
        assert ast.operand.value == "1"

    def test_no_operator_after_opening(self):
        with pytest.raises(ParseError, match="Operator after opening bracket"):
            parse_expression("(* 1)")

    def test_no_operator_after_comma(self):
        ast = parse_expression("(1, +2)")
        assert isinstance(ast, BracketList)
        assert len(ast.elements) == 2
        assert isinstance(ast.elements[0], Literal)
        assert ast.elements[0].value == "1"
        assert isinstance(ast.elements[1], UnaryOp)
        assert ast.elements[1].operator == "+"
        assert isinstance(ast.elements[1].operand, Literal)
        assert ast.elements[1].operand.value == "2"

        with pytest.raises(ParseError, match="Operator after comma"):
            parse_expression("(1, *2)")

    def test_binary_expression(self):
        ast = parse_expression("${a} + 2")
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "+"
        assert isinstance(ast.left, Variable)
        assert ast.left.name == "a"
        assert isinstance(ast.right, Literal)
        assert ast.right.value == "2"

    def test_function_call(self):
        ast = parse_expression("regex(${field}, '^[0-9]+$')")
        assert isinstance(ast, Call)
        assert isinstance(ast.callee, Identifier)
        assert ast.callee.name == "regex"
        assert len(ast.args) == 2
        assert isinstance(ast.args[0], Variable)
        assert isinstance(ast.args[1], Literal)

    def test_hyphen_in_identifier_unknown_function(self):
        with pytest.raises(ParseError, match="Unknown function `my-function`"):
            parse_expression("my-function(${arg})")

    def test_invalid_number_params(self):
        with pytest.raises(
            ParseError, match="Invalid number of function arguments `string-length`"
        ):
            parse_expression("string-length(${arg}, 'hello')")

    def test_hyphen_in_identifier(self):
        ast = parse_expression("string-length(${arg})")
        assert isinstance(ast, Call)
        assert isinstance(ast.callee, Identifier)
        assert ast.callee.name == "string-length"
        assert len(ast.args) == 1
        assert isinstance(ast.args[0], Variable)
        assert ast.args[0].name == "arg"

    def test_dynamic_function_name(self):
        with pytest.raises(ParseError, match="Unexpected token"):
            parse_expression("substr('hello', 1, 5)(${arg})")

    def test_not_supported_xlsform_function(self) -> None:
        with pytest.raises(
            ParseError, match="Function not supported in QGIS expressions `digest`"
        ):
            parse_expression("digest('abcd', 'key')")

    def test_concatenate_function(self):
        ast = parse_expression("concat(${first_name})")
        assert isinstance(ast, Call)
        assert isinstance(ast.callee, Identifier)
        assert ast.callee.name == "concat"
        assert len(ast.args) == 1
        assert isinstance(ast.args[0], Variable)
        assert ast.args[0].name == "first_name"

        ast = parse_expression("concat(${first_name}, ' ', ${last_name})")
        assert isinstance(ast, Call)
        assert isinstance(ast.callee, Identifier)
        assert ast.callee.name == "concat"
        assert len(ast.args) == 3
        assert isinstance(ast.args[0], Variable)
        assert ast.args[0].name == "first_name"
        assert isinstance(ast.args[1], Literal)
        assert ast.args[1].value == " "
        assert isinstance(ast.args[2], Variable)
        assert ast.args[2].name == "last_name"


class TestTemplateParser:
    def test_template_with_text_only(self):
        ast = parse_template("Hello Santa, welcome!")

        assert isinstance(ast, Template)
        assert len(ast.elements) == 1
        assert isinstance(ast.elements[0], Literal)
        assert ast.elements[0].type == LiteralType.STRING
        assert ast.elements[0].value == "Hello Santa, welcome!"
        assert ast.elements[0].raw_value == "Hello Santa, welcome!"

    def test_template_with_variable_and_text(self):
        ast = parse_template("Hello ${name}, welcome!")

        assert isinstance(ast, Template)
        assert len(ast.elements) == 3
        assert isinstance(ast.elements[0], Literal)
        assert ast.elements[0].value == "Hello "
        assert isinstance(ast.elements[1], Variable)
        assert ast.elements[1].name == "name"
        assert isinstance(ast.elements[2], Literal)
        assert ast.elements[2].value == ", welcome!"
