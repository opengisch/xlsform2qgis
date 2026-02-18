from unittest.mock import MagicMock

import pytest

from xlsform2qgis.expressions.registry import SUPPORTED_FUNCTIONS, register_function


def test_register_function_without_parentheses_infers_params():
    name = "tmp-registry-infer"

    try:

        @register_function
        def tmp_registry_infer(value: str, ctx) -> str:
            return f"upper({value})"

        ctx = MagicMock()

        spec = SUPPORTED_FUNCTIONS[name]
        assert spec.validate(1)
        assert not spec.validate(0)
        assert not spec.validate(2)
        assert spec.format(name, "'abc'", ctx=ctx) == "upper('abc')"
    finally:
        SUPPORTED_FUNCTIONS.pop(name, None)


def test_register_function_with_explicit_params():
    name = "tmp-registry-explicit"

    try:

        @register_function(name=name, params=[3, 5])
        def tmp_registry_explicit(*args: str, ctx) -> str:
            return f"args_{len(args)}"

        ctx = MagicMock()

        spec = SUPPORTED_FUNCTIONS[name]
        assert spec.validate(3)
        assert not spec.validate(4)
        assert spec.validate(5)
        assert spec.format(name, "a", "b", "c", ctx=ctx) == "args_3"
    finally:
        SUPPORTED_FUNCTIONS.pop(name, None)


def test_builtin_specs_store_expected_args_count():
    assert SUPPORTED_FUNCTIONS["regex"].expected_args_count == 2
    assert SUPPORTED_FUNCTIONS["substr"].expected_args_count == (2, 3)
    assert callable(SUPPORTED_FUNCTIONS["indexed-repeat"].expected_args_count)


def test_register_function_duplicate_name_raises_assertion_error():
    name = "tmp-registry-duplicate"

    try:

        @register_function(name=name)
        def tmp_registry_duplicate_a(value: str, ctx) -> str:
            return value

        with pytest.raises(
            AssertionError, match=f"Function {name} already registered!"
        ):

            @register_function(name=name)
            def tmp_registry_duplicate_b(value: str, ctx) -> str:
                return value
    finally:
        SUPPORTED_FUNCTIONS.pop(name, None)
