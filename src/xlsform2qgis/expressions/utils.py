_DATE_FORMATS = {
    r"%Y": "yyyy",
    r"%y": "yy",
    r"%m": "MM",
    r"%n": "M",
    r"%b": "MMM",
    r"%d": "dd",
    r"%e": "d",
    r"%a": "ddd",
}
_DATETIME_FORMATS = {
    **_DATE_FORMATS,
    r"%H": "HH",
    r"%h": "H",
    r"%M": "mm",
    r"%S": "ss",
    r"%3": "zzz",
}

DOUBLE_QUOTE = '"'
SINGLE_QUOTE = "'"


def convert_date_format(xlsform_format: str) -> str:
    for xls_code, qgis_code in _DATE_FORMATS.items():
        xlsform_format = xlsform_format.replace(xls_code, qgis_code)

    return xlsform_format


def convert_datetime_format(xlsform_format: str) -> str:
    for xls_code, qgis_code in _DATETIME_FORMATS.items():
        xlsform_format = xlsform_format.replace(xls_code, qgis_code)

    return xlsform_format


def wrap_field(field_name: str, quote_char: str = DOUBLE_QUOTE) -> str:
    # QGIS uses double quotes to escape field names, but if the field name itself contains a double quote,
    # we need to escape it by doubling it (e.g. field name `he"llo` would be escaped as `"he""llo"`
    # Same goes for single quotes when used to wrap strings.
    field_name = field_name.replace(quote_char, quote_char + quote_char)
    return f"{quote_char}{field_name}{quote_char}"
