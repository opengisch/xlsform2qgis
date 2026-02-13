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
