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


def convert_date_format(xlsform_format: str) -> str:
    for xls_code, qgis_code in _DATE_FORMATS.items():
        xlsform_format = xlsform_format.replace(xls_code, qgis_code)

    return xlsform_format


def convert_datetime_format(xlsform_format: str) -> str:
    for xls_code, qgis_code in _DATETIME_FORMATS.items():
        xlsform_format = xlsform_format.replace(xls_code, qgis_code)

    return xlsform_format
