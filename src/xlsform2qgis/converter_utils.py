import re

from io import StringIO
from html.parser import HTMLParser


class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = StringIO()

    def handle_data(self, data):
        self.text.write(data)

    def get_data(self):
        return self.text.getvalue()


def strip_html(html: str) -> str:
    s = HTMLStripper()
    s.feed(html)
    return s.get_data()


def parse_xlsform_range_parameters(
    xlsform_parameters: str,
) -> tuple[float, float, float]:
    start_match = re.search(
        r"start=\s*([0-9]+)", xlsform_parameters, flags=re.IGNORECASE
    )
    end_match = re.search(r"end=\s*([0-9]+)", xlsform_parameters, flags=re.IGNORECASE)
    step_match = re.search(r"step=\s*([0-9]+)", xlsform_parameters, flags=re.IGNORECASE)

    if start_match is None:
        start = 0.0
    else:
        start = float(start_match.group(1))

    if end_match is None:
        end = 10.0
    else:
        end = float(end_match.group(1))

    if step_match is None:
        step = 1.0
    else:
        step = float(step_match.group(1))

    return start, end, step


def parse_xlsform_select_from_file_parameters(
    xlsform_parameters: str,
) -> tuple[str, str]:
    match = re.search(r"(?:value)\s*=\s*([^\s]*)", xlsform_parameters)
    if match:
        list_key = match.group(1)
    else:
        list_key = "name"

    match = re.search(r"(?:label)\s*=\s*([^\s]*)", xlsform_parameters)
    if match:
        list_value = match.group(1)
    else:
        list_value = "label"

    return list_key, list_value
