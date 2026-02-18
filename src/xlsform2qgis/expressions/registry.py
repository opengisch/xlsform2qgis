from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, cast, overload

from xlsform2qgis.expressions.utils import (
    convert_date_format,
    convert_datetime_format,
    wrap_field,
)

if TYPE_CHECKING:
    from xlsform2qgis.expressions.expression import ExpressionContext


_NULL = "NULL"


class FunctionSpec:
    expression: str | Callable[..., str] | None

    _expected_args_count: Callable[[int], bool] | int | tuple[int, int | None]
    _validate_function: Callable[[int], bool]

    def __init__(
        self,
        args_count: Callable[[int], bool] | int | tuple[int, int | None],
        qgis_expression: str | Callable[..., str] | None,
    ) -> None:
        self._expected_args_count = args_count

        if callable(args_count):
            self._validate_function = args_count
        elif isinstance(args_count, (tuple, int)):
            self._validate_function = self._validate_arg_count
        else:
            raise ValueError(
                f"Invalid argument for `FunctionSpec`, expected int, tuple[int, int], or callable, got {type(args_count)}"
            )

        self.expression = qgis_expression

    def _validate_arg_count(self, count: int) -> bool:
        if isinstance(self._expected_args_count, int):
            min_args, max_args = self._expected_args_count, self._expected_args_count
        elif isinstance(self._expected_args_count, tuple):
            min_args, max_args = cast(tuple[int, int], self._expected_args_count)
        else:
            raise AssertionError("Unexpected type for `self._expected_args_count`")

        if count < min_args:
            return False

        if max_args is not None and count > max_args:
            return False

        return True

    def validate(self, count: int) -> bool:
        return self._validate_function(count)

    @property
    def expected_args_count(
        self,
    ) -> Callable[[int], bool] | int | tuple[int, int | None]:
        return self._expected_args_count

    def args_count(self) -> int:
        if callable(self.expression):
            return -1

        expression = self.expression or ""
        return len(re.findall(r"(?<!\{)\{(\d+)\}(?!\})", expression))

    def format(self, /, *args: str, ctx: ExpressionContext) -> str:
        if self.expression is None:
            raise ValueError("Cannot format expression for unsupported function")

        args_count = self.args_count()

        if callable(self.expression):
            assert args_count == -1

            result = self.expression(*args, ctx=ctx)

            if result is None:
                return "NULL"
            else:
                return result.format(*args)

        if len(args) > args_count + 1:
            raise ValueError(
                f"Expected at most {args_count} arguments, got {len(args)}"
            )

        while len(args) < args_count:
            args += ("NULL",)

        return self.expression.format(*args)


def _indexed_repeat_args_count(count: int) -> bool:
    return count in {3, 5, 7}


def _weighted_checklist_args_count(count: int) -> bool:
    return count >= 4 and (count - 2) % 2 == 0


SUPPORTED_FUNCTIONS: dict[str, FunctionSpec]
"""Mapping of supported xlsform function names and their argument contracts/QGIS equivalents."""

SUPPORTED_FUNCTIONS = {
    "if": FunctionSpec(3, "if({1}, {2}, {3})"),
    "position": FunctionSpec(1, None),
    "once": FunctionSpec(1, None),
    "selected": FunctionSpec(
        2,
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
    "indexed-repeat": FunctionSpec(_indexed_repeat_args_count, None),
    "count": FunctionSpec(1, "array_length({1})"),
    "count-non-empty": FunctionSpec(1, "array_length({1}) - count_missing({1})"),
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
    "normalize-space": FunctionSpec(1, "trim( regexp_replace( {1}, '\\s+', ' ') )"),
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
    "area": FunctionSpec(1, "area({1})"),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#distance
    "distance": FunctionSpec((1, None), None),
    "geofence": FunctionSpec(2, "contains({2}, {1})"),
    "random": FunctionSpec(0, "randf()"),
    "randomize": FunctionSpec((1, 2), "array_get({1}, rand(0, array_length({1}) - 1))"),
    "boolean": FunctionSpec(1, "to_bool({1})"),
    "not": FunctionSpec(1, "not {1}"),
    "coalesce": FunctionSpec(2, "coalesce({1}, {2})"),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#checklist
    "checklist": FunctionSpec((3, None), None),
    # TODO @suricactus: implement https://docs.getodk.org/form-operators-functions/#weighted-checklist
    "weighted-checklist": FunctionSpec(_weighted_checklist_args_count, None),
    "true": FunctionSpec(0, "true"),
    "false": FunctionSpec(0, "false"),
}


def _args_to_placeholders(args) -> str:
    return ", ".join(f"{{{i}}}" for i in range(1, len(args) + 1))


def _to_args_count(params: list[int]) -> Callable[[int], bool] | int:
    allowed = sorted(set(params))
    if len(allowed) == 1:
        return allowed[0]

    allowed_set = set(allowed)

    def validate_count(count: int) -> bool:
        return count in allowed_set

    return validate_count


def _infer_params(func: Callable[..., str]) -> list[int]:
    signature = inspect.signature(func)

    min_args = 0
    max_args = 0

    for param in signature.parameters.values():
        if param.name == "ctx":
            continue

        if param.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            if param.default is inspect.Parameter.empty:
                min_args += 1
            max_args += 1
            continue

        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            raise ValueError(
                f"Cannot infer parameter counts for `{func.__name__}` with `*args`; pass `params=[...]` explicitly."
            )

    return list(range(min_args, max_args + 1))


def _normalize_params(func: Callable[..., str], params: list[int] | None) -> list[int]:
    if params is None:
        params = _infer_params(func)

    if not params:
        raise ValueError("`params` cannot be empty")
    if any(param < 0 for param in params):
        raise ValueError("`params` must contain non-negative integers")

    return sorted(set(params))


def _wrap_registered_function(
    func: Callable[..., str],
) -> Callable[..., str]:
    # `FunctionSpec.format` passes function name as first argument; decorators expose a cleaner API
    # where registered callables only define XLSForm function arguments.
    def wrapped(*args: str, ctx: ExpressionContext) -> str:
        return func(*args[1:], ctx=ctx)

    return wrapped


@overload
def register_function(
    func: Callable[..., str],
    /,
) -> Callable[..., str]: ...


@overload
def register_function(
    *,
    name: str | None = None,
    params: list[int] | None = None,
    args_count: Callable[[int], bool] | int | tuple[int, int | None] | None = None,
) -> Callable[[Callable[..., str]], Callable[..., str]]: ...


def register_function(
    func: Callable[..., str] | None = None,
    /,
    *,
    name: str | None = None,
    params: list[int] | None = None,
    args_count: Callable[[int], bool] | int | tuple[int, int | None] | None = None,
) -> Callable[..., str] | Callable[[Callable[..., str]], Callable[..., str]]:
    def decorator(target: Callable[..., str]) -> Callable[..., str]:
        if args_count is not None and params is not None:
            raise ValueError("Pass either `params` or `args_count`, not both")

        effective_args_count = (
            _to_args_count(_normalize_params(target, params))
            if args_count is None
            else args_count
        )

        function_name = name or target.__name__.replace("_", "-")

        assert function_name not in SUPPORTED_FUNCTIONS, (
            f"Function {function_name} already registered!"
        )

        SUPPORTED_FUNCTIONS[function_name] = FunctionSpec(
            effective_args_count,
            _wrap_registered_function(target),
        )
        return target

    if func is not None:
        return decorator(func)

    return decorator


@register_function(name="string-length", args_count=(0, 1))
def string_length(*args: str, ctx: ExpressionContext) -> str:
    assert len(args) in (0, 1)

    if args:
        return f"length({args[0]})"
    else:
        return f"length({wrap_field(ctx.current_field)})"


@register_function(name="concat", args_count=(1, None))
def concat(*args: str, ctx: ExpressionContext) -> str:
    return "concat({})".format(_args_to_placeholders(args))


@register_function(name="format-date")
def format_date(date: str, fmt: str, ctx: ExpressionContext) -> str:
    return f"format_date(to_date({date}), {convert_date_format(fmt)})"


@register_function(name="format-date-time")
def format_date_time(date: str, fmt: str, ctx: ExpressionContext) -> str:
    return f"format_date(to_datetime({date}), {convert_datetime_format(fmt)})"


@register_function(name="pulldata", params=[3, 4, 5])
def pulldata(*args: str, ctx: ExpressionContext) -> str:
    assert len(args) in (3, 4, 5)

    # TODO @suricactus: implement full spec https://xlsform.org/en/#how-to-pull-data-from-csv
    if args[0] == "'@geopoint'":
        looking_for = args[2].strip().lower()

        if looking_for == "'accuracy'":
            return "@position_horizontal_accuracy"
        if looking_for == "'x'":
            return "$x"
        if looking_for == "'y'":
            return "$y"

    raise ValueError(
        f"Unsupported implementation of pulldata with parameters {args} in QGIS expressions!"
    )


@register_function(name="uuid", params=[0, 1])
def uuid(*args: str, ctx: ExpressionContext) -> str:
    assert len(args) in (0, 1)

    if not args:
        return "uuid(format:='WithoutBraces')"

    return "substr(repeat(uuid(format:='WithoutBraces'), ceil({1} / 32)), 1, {1})"


@register_function(name="jr:choice-name")
def jr_choice_name(choice_value: str, list_name: str, ctx: ExpressionContext) -> str:
    list_name = list_name.strip("'")

    if list_name not in ctx.choices_by_list:
        raise ValueError(
            f"Unknown choices list {list_name}, expected one of {list(ctx.choices_by_list.keys())}!"
        )

    for choice in ctx.choices_by_list[list_name]:
        assert "name" in choice
        assert "label" in choice

        if choice["name"] == choice_value:
            return choice["label"]

    raise ValueError(f"Value `{choice_value}` not found in {list_name}!")


@register_function(name="min", args_count=(1, None))
def min(*args: str, ctx: ExpressionContext) -> str:
    return "min({})".format(_args_to_placeholders(args))


@register_function(name="max", args_count=(1, None))
def max(*args: str, ctx: ExpressionContext) -> str:
    return "max({})".format(_args_to_placeholders(args))


@register_function(name="sum", args_count=(1, None))
def sum(*args: str, ctx: ExpressionContext) -> str:
    return "sum({})".format(_args_to_placeholders(args))


@register_function(name="version")
def version(ctx: ExpressionContext) -> str:
    return ctx.survey_settings.get("version", _NULL)
