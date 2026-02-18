import json
import logging
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from json2qgis.generate import (
    generate_field_def,
    generate_form_item_def,
    generate_layer_def,
    generate_relation_def,
    generate_uuid_field_def,
)
from json2qgis.type_defs import (
    AliasDef,
    ChoicesDef,
    ConstraintStrength,
    FieldDef,
    FormItemDef,
    FormItemGroupTypes,
    GeometryType,
    LayerDef,
    LayerTreeItemDef,
    PathOrStr,
    RelationDef,
    WeakFieldDef,
    WeakFormItemDef,
    WeakLayerDef,
)
from qgis.core import (
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QObject, QVariant, pyqtSignal

from xlsform2qgis.converter_utils import (
    build_choices_layer_id,
    get_xlsform_type,
    parse_xlsform_range_parameters,
    parse_xlsform_select_from_file_parameters,
    strip_html,
)
from xlsform2qgis.expressions.expression import (
    Expression,
    ExpressionContext,
    ParserType,
    QgisRenderType,
)
from xlsform2qgis.expressions.parser import ParseError
from xlsform2qgis.sheet_parser import ParsedSheetRow
from xlsform2qgis.type_defs import (
    GroupStatus,
    LayerStatus,
    XlsformSettings,
)

if TYPE_CHECKING:
    from xlsform2qgis.converter import XlsFormConverter


@dataclass
class WidgetContext:
    converter: "XlsFormConverter"
    row: ParsedSheetRow


class ParsedRow:
    def __init__(
        self,
        layer: WeakLayerDef | None = None,
        relation: dict[str, Any] | None = None,
        field: WeakFieldDef | None = None,
        form_field: WeakFormItemDef | None = None,
        form_container: dict[str, Any] | None = None,
        geometry_type: GeometryType | None = None,
        group_status: GroupStatus = GroupStatus.NONE,
        layer_status: LayerStatus = LayerStatus.NONE,
    ) -> None:
        self.layer = layer or {}
        self.relation = relation or {}
        self.field = field or {}
        self.form_field = form_field or {}
        self.form_container = form_container or {}
        self.geometry_type: GeometryType | None = geometry_type
        self.group_status = group_status
        self.layer_status = layer_status


class WidgetRegistry:
    """Singleton registry for widget type callbacks."""

    _instance = None
    _registry: dict[str, Callable[[WidgetContext], ParsedRow]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)

        return cls._instance

    def register(
        self,
        widget_type: str,
        func: Callable[[WidgetContext], ParsedRow],
    ) -> None:
        self._registry[widget_type] = func

    def get(
        self,
        widget_type: str,
        is_strict: bool = False,
    ) -> Callable[[WidgetContext], ParsedRow] | None:
        cb = self._registry.get(widget_type)

        if not cb and not is_strict:
            cb = self._registry.get(get_xlsform_type(widget_type))

        return cb


def register_type(
    format_name: list[str],
) -> Callable[
    [Callable[[WidgetContext], ParsedRow]], Callable[[WidgetContext], ParsedRow]
]:
    widget_registry = WidgetRegistry()

    def decorator(
        func: Callable[[WidgetContext], ParsedRow],
    ) -> Callable[[WidgetContext], ParsedRow]:
        for widget_type in format_name:
            if widget_registry.get(widget_type, is_strict=True):
                raise ValueError(f"Widget type {widget_type} already registered!")

            widget_registry.register(widget_type, func)

        return func

    return decorator


@register_type(["calculate"])
def widget_calculate(ctx: WidgetContext) -> ParsedRow:
    form_item: WeakFieldDef = {}

    if ctx.row["calculation"]:
        form_item.update(
            {
                "default_value": ctx.converter.get_expression(
                    ctx.row["calculation"],
                    str(ctx.row["name"]),
                    should_strip_tags=True,
                ).to_qgis(),
                "set_default_value_on_update": True,
            }
        )

    if ctx.converter._get_label(ctx.row):
        widget_type = "TextEdit"
        show_label = True
    else:
        widget_type = "Hidden"
        show_label = False

    return ParsedRow(
        field={
            "widget_type": widget_type,
            **form_item,
        },
        form_field={
            "is_read_only": True,
            "show_label": show_label,
        },
    )


@register_type(["hidden"])
def widget_hidden(ctx: WidgetContext) -> ParsedRow:
    field: WeakFieldDef = {}

    if ctx.row["calculation"]:
        default_value_expr = ctx.converter.get_expression(
            ctx.row["calculation"], str(ctx.row["name"])
        )

        field.update(
            {
                "default_value": default_value_expr.to_qgis(),
                "set_default_value_on_update": True,
            }
        )

    return ParsedRow(
        field={
            "widget_type": "Hidden",
            **field,
        },
        form_field={
            "show_label": False,
            "is_read_only": True,
        },
    )


@register_type(["today"])
def widget_today(ctx: WidgetContext) -> ParsedRow:
    return ParsedRow(
        field={
            "type": "date",
            "name": ctx.row["name"],
            "widget_type": "Hidden",
            "default_value": "format_date(now(), 'yyyy-MM-dd')",
            "set_default_value_on_update": False,
        },
        form_field={
            "show_label": False,
            "is_read_only": True,
        },
    )


@register_type(["start"])
def widget_start(ctx: WidgetContext) -> ParsedRow:
    return ParsedRow(
        field={
            "type": "datetime",
            "name": ctx.row["name"],
            "widget_type": "Hidden",
            "default_value": "format_date(now(), 'yyyy-MM-dd hh:mm:ss')",
            "set_default_value_on_update": False,
        },
        form_field={
            "show_label": False,
            "is_read_only": True,
        },
    )


@register_type(["end"])
def widget_end(ctx: WidgetContext) -> ParsedRow:
    return ParsedRow(
        field={
            "type": "datetime",
            "name": ctx.row["name"],
            "widget_type": "Hidden",
            "default_value": "format_date(now(), 'yyyy-MM-dd hh:mm:ss')",
            "set_default_value_on_update": True,
        },
        form_field={
            "show_label": False,
            "is_read_only": True,
        },
    )


@register_type(["username"])
def widget_username(ctx: WidgetContext) -> ParsedRow:
    return ParsedRow(
        field={
            "type": "string",
            "name": ctx.row["name"],
            "widget_type": "Hidden",
            "default_value": "@cloud_username",
            "set_default_value_on_update": False,
        },
        form_field={
            "show_label": False,
            "is_read_only": True,
        },
    )


@register_type(["email"])
def widget_email(ctx: WidgetContext) -> ParsedRow:
    return ParsedRow(
        field={
            "type": "string",
            "name": ctx.row["name"],
            "widget_type": "Hidden",
            "default_value": "@cloud_useremail",
            "set_default_value_on_update": False,
        },
        form_field={
            "show_label": False,
            "is_read_only": True,
        },
    )


@register_type(["text", "barcode"])
def widget_text(ctx: WidgetContext) -> ParsedRow:
    widget_config = {}
    if ctx.row["appearance"] == "multiline":
        widget_config.update(
            {
                "IsMultiline": True,
            }
        )

    return ParsedRow(
        field={
            "type": "string",
            "widget_type": "TextEdit",
            "widget_config": widget_config,
        },
    )


@register_type(["acknowledge"])
def widget_acknowledge(ctx: WidgetContext) -> ParsedRow:
    return ParsedRow(
        field={
            "widget_type": "CheckBox",
        }
    )


@register_type(["integer", "decimal"])
def widget_numeric(ctx: WidgetContext) -> ParsedRow:
    return ParsedRow(
        field={
            "widget_type": "Range",
        }
    )


@register_type(["range"])
def widget_range(ctx: WidgetContext) -> ParsedRow:
    if ctx.row["parameters"]:
        start, end, step = parse_xlsform_range_parameters(ctx.row["parameters"])

        widget_config = {
            "Min": start,
            "Max": end,
            "Step": step,
            "Type": "Slider",
        }
    else:
        widget_config = {}

    return ParsedRow(
        field={
            "widget_type": "Range",
            "widget_config": widget_config,
        }
    )


@register_type(["date", "time", "datetime"])
def widget_datetime(ctx: WidgetContext) -> ParsedRow:
    row_type = ctx.row["type"].lower()

    if row_type == "date":
        datetime_format = "yyyy-MM-dd"
    elif row_type == "time":
        datetime_format = "HH:mm:ss"
    elif row_type == "datetime":
        datetime_format = "yyyy-MM-dd HH:mm:ss"
    else:
        raise ValueError(f"Unsupported xlsform type for date/time: {ctx.row['type']}")

    return ParsedRow(
        field={
            "widget_type": "DateTime",
            "widget_config": {
                "field_format_overwrite": True,
                "display_format": datetime_format,
                "field_format": datetime_format,
                "allow_null": True,
                "calendar_popup": True,
            },
        }
    )


@register_type(["image", "audio", "video", "background-audio", "file"])
def widget_media(ctx: WidgetContext) -> ParsedRow:
    if ctx.row["type"] == "image":
        document_viewer = 1
    elif ctx.row["type"] in ("audio", "background-audio"):
        document_viewer = 2
    elif ctx.row["type"] == "video":
        document_viewer = 3
    else:
        document_viewer = 0

    return ParsedRow(
        field={
            "widget_type": "ExternalResource",
            "widget_config": {
                "DocumentViewer": document_viewer,
                "FileWidget": True,
                "FileWidgetButton": True,
                "RelativeStorage": 1,
            },
        }
    )


@register_type(
    [
        "select_one",
        "select_multiple",
        "select_one_from_file",
        "select_multiple_from_file",
    ]
)
def widget_select_from_file(ctx: WidgetContext) -> ParsedRow:
    layer: WeakLayerDef = {}
    xlsform_type, *type_details = str(ctx.row["type"]).strip().split(" ")
    layer_id = build_choices_layer_id(*type_details)

    if xlsform_type in (
        "select_one_from_file",
        "select_multiple_from_file",
    ):
        list_key, list_value = parse_xlsform_select_from_file_parameters(
            ctx.row["parameters"]
        )

        raise NotImplementedError(
            "select_from_file and select_multiple_from_file not implemented yet"
        )
        # layers.append(
        #     generate_layer_def(
        #         id=layer_id,
        #         name=layer_id,
        #         fields=fields_def,
        #         is_private=True,
        #         custom_properties={
        #             "QFieldSync/cloud_action": "no_action",
        #             "QFieldSync/action": "copy",
        #         },
        #         data=list_choices,
        #         # TODO @suricactus: build the layer properly
        #     )
        # )

    else:
        list_key = "name"
        list_value = "label"

        assert ctx.converter.find_layer(layer_id)

    filter_expressions = []
    choice_filter_expr = ctx.converter.get_expression(
        ctx.row["choice_filter"] or "",
        ctx.row["name"],
    )
    filter_expressions.append(choice_filter_expr.to_qgis(use_current=True))

    if xlsform_type in ("select_multiple", "select_multiple_from_file"):
        allow_multi = True

        # TODO @suricactus: why do we need this expression?
        filter_expressions.append(f""" "{list_key}" != '' """)
    else:
        allow_multi = False

    filter_expression = " AND ".join(
        # join together all non-empty filter expressions, as the first element might be an empty string
        [fe for fe in filter_expressions if fe]
    )

    return ParsedRow(
        field={
            "widget_type": "ValueRelation",
            "widget_config": {
                "Layer": layer_id,
                "LayerName": type_details[0],
                # TODO @suricactus: confirm these are not required properties, as we already have the layer ID above
                # "LayerProviderName": "ogr",
                # "LayerSource": value_layer[0].source(),
                "Key": list_key,
                "Value": list_value,
                "AllowNull": False,
                "AllowMulti": allow_multi,
                "FilterExpression": filter_expression,
            },
        },
        layer=layer,
    )


@register_type(
    [
        "geopoint",
        "geotrace",
        "geoshape",
        "start-geopoint",
        "start-geotrace",
        "start-geoshape",
    ]
)
def widget_geometry(ctx: WidgetContext) -> ParsedRow:
    geom: GeometryType = "NoGeometry"

    if ctx.row["type"] in ("geopoint", "start-geopoint"):
        geom = "Point"

    if ctx.row["type"] in ("geotrace", "start-geotrace"):
        geom = "LineString"

    if ctx.row["type"] in ("geoshape", "start-geoshape"):
        geom = "Polygon"

    return ParsedRow(
        geometry_type=geom,
    )


@register_type(["begin group", "begin_group"])
def widget_begin_group(ctx: WidgetContext) -> ParsedRow:
    container_id = f"item_container_{ctx.row.idx}"
    label = strip_html(ctx.row["label"])

    return ParsedRow(
        form_container={
            "item_id": container_id,
            "label": label,
            "type": ctx.converter.get_form_group_type(),
        },
        group_status=GroupStatus.BEGIN,
    )


@register_type(["end group", "end_group"])
def widget_end_group(ctx: WidgetContext) -> ParsedRow:
    return ParsedRow(
        group_status=GroupStatus.END,
    )


@register_type(["note"])
def widget_note(ctx: WidgetContext) -> ParsedRow:
    container_id = f"item_container_{ctx.row.idx}"
    label_expr_str = ctx.row["label"] or ""
    label_expr = ctx.converter.get_expression(
        label_expr_str, str(ctx.row["name"]), ParserType.TEMPLATE
    )

    if label_expr.is_str():
        label = label_expr_str
    else:
        label = label_expr.to_qgis(expression_type=QgisRenderType.TEMPLATE)

    return ParsedRow(
        form_container={
            "item_id": container_id,
            "label": label,
            "type": "text",
            "is_markdown": False,
        },
    )


@register_type(["begin repeat", "begin_repeat"])
def widget_begin_repeat(ctx: WidgetContext) -> ParsedRow:
    layer_id = f"layer_repeat_{ctx.row.idx}"
    layer: WeakLayerDef = {
        "layer_id": layer_id,
        "name": f"repeat_{ctx.row['name']}",
        "primary_key": "uuid",
        "geometry_type": "NoGeometry",
        "layer_type": "vector",
        "fields": [
            generate_uuid_field_def(),
            generate_field_def(
                name="uuid_parent",
                type="string",
                alias="Parent UUID",
                widget_type="TextEdit",
            ),
        ],
        "is_private": True,
    }

    relation_id = f"relation_{ctx.row.idx}"
    relation = {
        "relation_id": relation_id,
        "name": relation_id,
        "to_layer_id": ctx.converter.layers[-1]["layer_id"],
        "from_layer_id": layer_id,
        "field_pairs": [
            {
                "to_field": "uuid",
                "from_field": "uuid_parent",
            }
        ],
    }

    form_field: WeakFormItemDef = {
        "item_id": relation_id,
        "field_name": relation_id,
        "type": "relation",
    }

    return ParsedRow(
        layer=layer,
        relation=relation,
        form_field=form_field,
        layer_status=LayerStatus.BEGIN,
    )


@register_type(
    ["end repeat", "end_repeat"],
)
def widget_end_repeat(ctx: WidgetContext) -> ParsedRow:
    return ParsedRow(
        layer_status=LayerStatus.END,
    )
