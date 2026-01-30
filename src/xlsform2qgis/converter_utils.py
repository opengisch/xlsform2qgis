from io import StringIO
import uuid
from html.parser import HTMLParser

from typing import cast

from xlsform2qgis.types import FieldDef, LayerDef, FormItemDef


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


def strip_tags(html: str) -> str:
    s = HTMLStripper()
    s.feed(html)
    return s.get_data()


def generate_field_def(**kwargs) -> FieldDef:
    return cast(
        FieldDef,
        {
            "id": str(uuid.uuid4()),
            "name": "",
            "type": "",
            "length": 0,
            "precision": 0,
            "comment": "",
            "is_not_null": False,
            "is_not_null_strength": "not_set",
            "constraint_expression": None,
            "constraint_expression_description": None,
            "constraint_expression_strength": "not_set",
            "is_unique": False,
            "is_unique_strength": "not_set",
            "default_value": None,
            "set_default_value_on_update": False,
            "alias": "",
            "widget_type": "",
            "widget_config": {},
            **kwargs,
        },
    )


def generate_layer_def(**kwargs) -> LayerDef:
    return cast(
        LayerDef,
        {
            "layer_id": str(uuid.uuid4()),
            "name": "",
            "geometry_type": "NoGeometry",
            "type": "vector",
            "crs": "EPSG:4326",
            "datasource_format": "memory",
            "fields": [],
            "form_config": [],
            "is_read_only": False,
            "is_identifiable": False,
            "is_private": False,
            "is_searchable": False,
            "is_removable": True,
            **kwargs,
        },
    )


def generate_form_item_def(**kwargs) -> FormItemDef:
    return cast(
        FormItemDef,
        {
            "id": str(uuid.uuid4()),
            "name": "",
            "type": "group_box",
            "parent_id": None,
            "visibility_expression": "",
            "background_color": "",
            "is_collapsed": False,
            "column_count": 1,
            "is_markdown": False,
            **kwargs,
        },
    )
