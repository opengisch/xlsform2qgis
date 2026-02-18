import json
import logging
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from json2qgis.generate import (
    generate_field_def,
    generate_form_item_def,
    generate_layer_def,
    generate_relation_def,
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
from xlsform2qgis.type_defs import (
    GroupStatus,
    LayerStatus,
    XlsformSettings,
)

# try:
#     import markdown  # type: ignore
# except ImportError:
#     pass


logger = logging.getLogger(__name__)


def generate_uuid_field_def(**kwargs: Any) -> FieldDef:
    field_def = generate_field_def(
        name="uuid",
        type="string",
        alias="UUID",
        default_value="uuid(format:='WithoutBraces')",
        widget_type="TextEdit",
    )

    return {
        **field_def,
        **kwargs,
    }


XLS_TYPES_MAP = {
    "integer": "integer",
    "decimal": "real",
    "range": "real",
    "date": "date",
    "today": "date",
    "time": "time",
    "datetime": "datetime",
    "start": "datetime",
    "end": "datetime",
    "acknowledge": "boolean",
    "text": "string",
    "barcode": "string",
    "image": "string",
    "audio": "string",
    "background-audio": "string",
    "video": "string",
    "file": "string",
    "select_one": "string",
    "select_one_from_file": "string",
    "select_multiple": "string",
    "select_multiple_from_file": "string",
    "rank": "string",
    "calculate": "string",
    "hidden": "string",
}

XLSFORM_COLS_BY_SHEET_NAME = {
    "survey": [
        "type",
        "name",
        "label",
        "calculation",
        "relevant",
        "choice_filter",
        "parameters",
        "constraint",
        "constraint_message",
        "required",
        "default",
        "is_read_only",
        "trigger",
        "appearance",
    ],
    "choices": [
        "list_name",
        "name",
        "label",
    ],
    "settings": [
        "form_title",
        "form_id",
        "default_language",
    ],
}


class ParsedSheetRow(dict[str, Any]):
    idx: int
    """We add a magical `idx` attribute to help identify the row in error messages and create unique identifiers"""

    def __init__(self, *args: Any, idx: int = -1, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.idx = idx


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


class ParsedSheet:
    skip_first_row: bool = False
    indices: dict[str, int]
    name: str

    def __init__(self, name: str, xlsform_filename: PathOrStr) -> None:
        self.name = name
        self.indices = defaultdict(lambda: -1)

        if self.name not in XLSFORM_COLS_BY_SHEET_NAME:
            raise ValueError(f"Unexpected sheet name {self.name}!")

        self.layer = QgsVectorLayer(
            str(xlsform_filename)
            + f"|layername={self.name}|option:FIELD_TYPES=STRING|option:HEADERS=FORCE",
            self.name,
            "ogr",
        )

        if not self.layer.isValid():
            raise ValueError(f"Failed to load layer from: {xlsform_filename}")

        fields_names: list[str | QVariant] = self.layer.fields().names()

        # if the first line in the xlsform is empty
        if fields_names[0] == "Field1":
            self.skip_first_row = True

            # expect at least one more line in the xlsform and use it as headers
            if self.layer.featureCount() > 1:
                fields_names = self.layer.getFeature(1).attributes()
            else:
                raise ValueError("Could not determine xlsform column headers!")

        if not len(fields_names) >= 2:
            raise ValueError("Sheet must have at least 2 columns: 'type', 'name'")

        for index, field_name in enumerate(fields_names):
            if isinstance(field_name, QVariant):
                assert field_name.isNull()

                continue

            if field_name == f"Field{index + 1}":
                logger.debug(
                    f"Skipping default field name `{field_name}` at index {index} in sheet `{self.name}`!"
                )

                continue

            normalized_field_name = re.sub(r"\s+", "_", str(field_name).strip().lower())

            if self.indices[normalized_field_name] != -1:
                logger.warning(
                    f"Column name `{normalized_field_name}` found both at index {self.indices[normalized_field_name]} and {index} in sheet `{self.name}`; will use the first occurrence!"
                )

                continue

            self.indices[normalized_field_name] = index

    def __iter__(self) -> Iterator[ParsedSheetRow]:
        it = cast(Iterable, self.layer.getFeatures())
        for idx, feat in enumerate(it):
            if idx == 0 and self.skip_first_row:
                continue

            row: ParsedSheetRow = ParsedSheetRow(idx=idx)

            for col in XLSFORM_COLS_BY_SHEET_NAME[self.name]:
                if self.indices[col] == -1:
                    row[col] = None
                else:
                    value = feat.attribute(self.indices[col])

                    if isinstance(value, QVariant):
                        if value.isNull():
                            value = None
                        else:
                            value = value.value()

                    row[col] = value

            for col_name, col_idx in self.indices.items():
                if col_idx == -1:
                    continue

                value = feat.attribute(col_idx)

                if isinstance(value, QVariant):
                    assert value.isNull()
                    value = None

                row[col_name] = value

            if not any(row.values()):
                logger.debug(
                    f"Skipping spreadsheet row with empty values at row index {idx} in sheet `{self.name}`!"
                )
                continue

            yield row


def parse_xlsform_sheets(
    xlsform_filename: PathOrStr,
) -> tuple[ParsedSheet, ParsedSheet, ParsedSheet]:
    """Extract the survey, choices and settings sheets from the given XLSForm file."""
    xlsform_filename = Path(xlsform_filename)
    if not xlsform_filename.exists():
        raise FileNotFoundError(f"XLSForm file not found: {xlsform_filename}")

    xlsform_filename = Path(xlsform_filename)
    if not xlsform_filename.exists():
        raise FileNotFoundError(f"XLSForm file not found: {xlsform_filename}")

    try:
        survey_sheet = ParsedSheet("survey", xlsform_filename)
        choices_sheet = ParsedSheet("choices", xlsform_filename)
        settings_sheet = ParsedSheet("settings", xlsform_filename)
    except ValueError as err:
        raise ValueError(
            f'Expected the provided spreadsheet to contain sheets named "survey", "choices" and "settings", but got an error: {err}'
        )

    return (survey_sheet, choices_sheet, settings_sheet)


def xlsform_to_json(
    xlsform_filename: PathOrStr, skip_failed_expressions: bool = False
) -> dict[str, Any]:
    survey_sheet, choices_sheet, settings_sheet = parse_xlsform_sheets(xlsform_filename)

    converter = XlsFormConverter(
        survey_sheet,
        choices_sheet,
        settings_sheet,
        skip_failed_expressions=skip_failed_expressions,
    )

    if not converter.is_valid():
        raise ValueError("Invalid XLSForm file!")

    return converter.to_json()


class XlsFormConverter(QObject):
    survey_sheet: ParsedSheet
    choices_sheet: ParsedSheet
    settings_sheet: ParsedSheet
    layers: list[LayerDef]
    layer_tree: list[LayerTreeItemDef]
    relations: list[RelationDef]

    info = pyqtSignal(str)
    warning = pyqtSignal(str)
    error = pyqtSignal(str)

    _settings: XlsformSettings
    """Settings as defined in the `settings` sheet of the XLSForm, with some defaults if not specified."""

    _skip_failed_expressions: bool
    """Return empty string instead of throwing an error when a row expression cannot be converted."""

    _calculate_expressions: dict[str, Expression]
    """Store the expressions for each `type=calculate` row, so they can be passed as `ExpressionContext` when needed."""

    _field_compatibilities: dict[str, bool]
    """Keep track of the compatibility of different XLSForm field types with QGIS and QField, to be able to emit warnings and info messages during the conversion process."""

    _form_group_type: FormItemGroupTypes = "group_box"
    """The form group type to use for non-root groups in the form. By default it is set to `group_box`, but it can be set to `tab` if the user prefers a more tabbed form structure."""

    _root_form_group_type: FormItemGroupTypes
    """Similar to `_form_group_type`, but specifically for the root level form groups, to allow more flexibility in the form structure definition. By default it is set to `tab` to encourage better form organization, but it can be set to `group_box` if the user prefers a flatter form structure."""

    _layer_ids: list[str]
    """Stack to keep track of the current layer ids while parsing the survey sheet, to be able to assign fields and form items to the correct layer. Whenever a new layer is defined, its id is pushed to the stack, and whenever a layer definition ends, it is popped from the stack."""

    _container_ids: list[str | None]
    """Stack to keep track of the current parent container ids while parsing the survey sheet, to be able to assign form items to the correct parent container. Whenever a new container is defined, its id is pushed to the stack, and whenever a container definition ends, it is popped from the stack. The value `None` is used to represent the root level, where there is no parent container."""

    def __init__(
        self,
        survey_sheet: ParsedSheet,
        choices_sheet: ParsedSheet,
        settings_sheet: ParsedSheet,
        parent: QObject | None = None,
        skip_failed_expressions: bool = False,
        form_group_type: FormItemGroupTypes = "group_box",
        root_form_group_type: FormItemGroupTypes = "tab",
    ) -> None:
        super().__init__(parent)

        self.survey_sheet = survey_sheet
        self.choices_sheet = choices_sheet
        self.settings_sheet = settings_sheet

        self._form_group_type = form_group_type
        self._root_form_group_type = root_form_group_type
        self._skip_failed_expressions = skip_failed_expressions
        self._calculate_expressions = {}

        self.layers = []
        self.layer_tree = []
        self.relations = []
        self._layer_ids = []
        self._container_ids = []

        self.widget_registry = WidgetRegistry()

        self._field_compatibilities = {}

    def is_valid(self) -> bool:
        if not self.survey_sheet.layer.isValid():
            return False

        # Missing the two basic parameters that must be present within the survey layer
        if self.survey_sheet.indices["type"] == -1:
            return False

        if self.survey_sheet.indices["name"] == -1:
            return False

        return True

    def find_layer(self, layer_id: str) -> LayerDef | None:
        for layer_def in self.layers:
            if layer_def["layer_id"] == layer_id:
                return layer_def

        return None

    def get_form_group_type(self) -> FormItemGroupTypes:
        if len(self._container_ids) == 0 or self._container_ids[-1] is None:
            return self._root_form_group_type

        return self._form_group_type

    def _get_expression_context(
        self,
        current_field: str,
        parser_type: ParserType = ParserType.EXPRESSION,
    ) -> ExpressionContext:
        return ExpressionContext(
            current_field=current_field,
            calculate_expressions=self._calculate_expressions,
            parser_type=parser_type,
            skip_expression_errors=self._skip_failed_expressions,
        )

    def get_expression(
        self,
        expression_str: str,
        current_field: str,
        parser_type: ParserType = ParserType.EXPRESSION,
        *,
        should_strip_tags: bool = True,
    ) -> Expression:
        try:
            return Expression(
                expression_str,
                self._get_expression_context(current_field, parser_type),
                should_strip_tags=should_strip_tags,
            )
        except ParseError as err:
            logger.error(
                f"Failed to parse expression `{expression_str}` for field `{current_field}`: {err}"
            )

            if self._skip_failed_expressions:
                return Expression(
                    "",
                    self._get_expression_context(current_field),
                    should_strip_tags=should_strip_tags,
                )

            raise

    def _enter_layer(self, layer_def: LayerDef) -> None:
        layer_id = layer_def["layer_id"]
        layer_name = layer_def["name"]

        self.layers.append(layer_def)
        self._layer_ids.append(layer_id)

        self._enter_container(None)

        self.layer_tree.append(
            {
                "layer_id": layer_id,
                "item_id": f"layer_{layer_id}",
                "name": layer_name,
                "parent_id": "",
                "type": "layer",
                "is_checked": True,
            }
        )

        form_item = generate_form_item_def(
            item_id=f"tab_item_{layer_id}",
            type=self.get_form_group_type(),
            label=layer_name,
            parent_id=None,
        )
        self._enter_container(form_item)

    def _exit_layer(self) -> str:
        layer_id = self._layer_ids.pop()

        self._exit_container()

        return layer_id

    def _current_layer(self) -> LayerDef:
        if not self._layer_ids:
            raise ValueError("No layers defined yet!")

        layer_id = self._layer_ids[-1]
        layer_def = self.find_layer(layer_id)

        if not layer_def:
            raise ValueError(f"Current layer with id {layer_id} not found!")

        return layer_def

    def _add_container(self, container_def: FormItemDef) -> None:
        self._current_layer()["form_config"].append(container_def)

    def _enter_container(self, container_def: FormItemDef | None) -> None:
        if container_def:
            self._add_container(container_def)

            self._container_ids.append(container_def["item_id"])
        else:
            self._container_ids.append(None)

    def _exit_container(self) -> str | None:
        item_id = self._container_ids.pop()

        return item_id

    def _current_container(self) -> FormItemDef | None:
        if not self._container_ids:
            raise ValueError("No form containers defined yet!")

        if self._container_ids[-1] is None:
            return None

        for form_item_def in reversed(self._current_layer()["form_config"]):
            if form_item_def["item_id"] == self._container_ids[-1]:
                return form_item_def

        raise AssertionError(
            f"Current container with id {self._container_ids[-1]} not found!"
        )

    def _get_label(self, sheet_row: ParsedSheetRow) -> str:
        default_language = self._settings["default_language"].lower()

        fallback_label = sheet_row.get("label", sheet_row["name"]) or ""

        if not default_language:
            logger.debug(
                "No default language specified, using `label` or `name` column as fallback."
            )

            return strip_html(fallback_label)

        label_key = f"label::{default_language}"

        if not sheet_row.get(label_key):
            logger.warning(
                f"No label found for default language `{default_language}`, using `label` or `name` column as fallback."
            )

        return strip_html(sheet_row.get(label_key, fallback_label) or "")

    def _get_field_def_alias(self, sheet_row: ParsedSheetRow) -> AliasDef:
        alias_str = self._get_label(sheet_row)

        if not alias_str:
            return {}

        alias_expression = self.get_expression(
            alias_str,
            sheet_row["name"],
            ParserType.TEMPLATE,
            should_strip_tags=True,
        )

        if alias_expression.is_str():
            return {
                "alias": alias_str,
            }
        else:
            return {
                "alias_expression": alias_expression.to_qgis(),
            }

    def _get_field_def(self, sheet_row: ParsedSheetRow) -> WeakFieldDef:
        field_def: WeakFieldDef = {}
        indices = self.survey_sheet.indices
        xlsform_type = get_xlsform_type(sheet_row["type"])
        field_name = str(sheet_row["name"]).strip()
        field_type = XLS_TYPES_MAP.get(xlsform_type, None)

        if not field_type:
            logger.debug(f"Couldn't determine the type for `{field_name}`!")

            return {}

        self._check_xlsform_type_compatibility(xlsform_type)

        constraint_expression = ""
        constraint_expression_description = ""
        constraint_expression_strength: ConstraintStrength = "not_set"

        if sheet_row["constraint"]:
            constraint_str = str(sheet_row["constraint"]).strip()
            constraint_expression = self.get_expression(
                constraint_str, field_name
            ).to_qgis()

            if constraint_expression:
                constraint_expression_strength = "hard"

            if sheet_row["constraint_message"]:
                constraint_expression_description = str(
                    sheet_row["constraint_message"]
                ).strip()

        is_not_null = False
        is_not_null_strength: ConstraintStrength = "not_set"

        if indices["required"] != -1:
            required_str = str(sheet_row["required"]).strip().lower()

            if required_str == "yes":
                is_not_null = True
                is_not_null_strength = "hard"

        field_def.update(cast(WeakFieldDef, self._get_field_def_alias(sheet_row)))

        # you cannot define both `calculation` and `default` at the same time, in such case use only `calculation`
        if sheet_row["calculation"] and sheet_row["default"]:
            self.warning.emit(
                "Both `calculation` and `default` are set; only calculation will be used"
            )

        # handle default value from either `calculation` or `default` column
        if sheet_row["calculation"]:
            default_value_expression = self.get_expression(
                sheet_row["calculation"], field_name
            ).to_qgis()

            field_def.update(
                {
                    "default_value": default_value_expression,
                    "set_default_value_on_update": False,
                }
            )
        elif sheet_row["default"]:
            if "${last-saved" not in sheet_row["default"]:
                is_digit = sheet_row["default"].replace(".", "", 1).isdigit()

                if is_digit:
                    default_value_expression = sheet_row["default"]
                else:
                    # TODO @suricactus: handle escaping of quotes inside the string
                    default_value_expression = f"'{sheet_row['default']}'"

                field_def.update(
                    {
                        "default_value": default_value_expression,
                        "set_default_value_on_update": False,
                    }
                )
            else:
                # TODO @suricactus: handle last-saved functionality, skipping for now
                pass

        return cast(
            WeakFieldDef,
            {
                **field_def,
                "name": field_name,
                "type": field_type,
                "is_not_null": is_not_null,
                "is_not_null_strength": is_not_null_strength,
                "constraint_expression": constraint_expression,
                "constraint_expression_description": constraint_expression_description,
                "constraint_expression_strength": constraint_expression_strength,
            },
        )

    def _check_xlsform_type_compatibility(self, xlsform_type: str) -> None:
        if xlsform_type in ("barcode",):
            if not self._field_compatibilities.get("barcode"):
                self._field_compatibilities["barcode"] = True

                self.info.emit(
                    self.tr(
                        "Barcode functionality is only available through QField; it will be a simple text field in QGIS"
                    )
                )
        elif xlsform_type in (
            "image",
            "audio",
            "video",
            "background-audio",
            "background-audio",
        ):
            if xlsform_type == "background-audio":
                self.warning.emit(
                    self.tr("Unsupported type background-audio, using audio instead")
                )

            if not self._field_compatibilities.get("media"):
                self._field_compatibilities["media"] = True
                self.info.emit(
                    self.tr(
                        "Multimedia content can be captured using QField on devices with cameras and microphones; in QGIS, pre-existing files can be selected."
                    )
                )

        elif xlsform_type in ("username", "email"):
            if not self._field_compatibilities.get("metadata"):
                self._field_compatibilities["metadata"] = True

                self.info.emit(
                    self.tr(
                        'The metadata "username" and "email" is only available through QFieldCloud; it will return an empty value in QGIS'.format()
                    )
                )
        else:
            # no compatibility warnings, horray!
            pass

    def _get_settings(self) -> XlsformSettings:
        settings_rows = list(self.settings_sheet)
        settings: XlsformSettings = {
            "form_title": "Untitled Survey",
            "form_id": "survey",
            "default_language": "",
            "version": datetime.now().isoformat(timespec="minutes"),
            "instance_name": '"uuid"',
        }

        if not settings_rows:
            return settings

        # let's assume there is only one row and ignore the rest
        settings_row = settings_rows[0]

        if settings_row.get("form_title"):
            settings["form_title"] = settings_row["form_title"]

        if settings_row.get("form_id"):
            settings["form_id"] = settings_row["form_id"]

        if settings_row.get("default_language"):
            settings["default_language"] = settings_row["default_language"]

        if settings_row.get("version"):
            settings["version"] = settings_row["version"]

        if settings_row.get("instance_name"):
            settings["instance_name"] = settings_row["instance_name"]

        return settings

    def get_display_expression(self, xlsform_expression: str | None) -> str:
        if not xlsform_expression:
            return ""

        display_expression = self.get_expression(
            xlsform_expression,
            "instance_name",
            ParserType.EXPRESSION,
        ).to_qgis()

        return display_expression

    def to_json(self) -> dict[str, Any]:
        self.convert()

        settings = self._get_settings()

        return {
            "project": {
                "custom_properties": {
                    "qfieldsync/maximumImageWidthHeight": 0,
                    "qfieldsync/initialMapMode": "digitize",
                },
                # TODO only if the EPSG is 3857 or any different from 4326
                # "display_settings": {
                #     "coordinate_type": "custom_crs",
                #     "custom_crs": "EPSG:4326",
                # },
                "author": "Ivan",
                "title": settings["form_title"],
            },
            "layers": self.layers,
            "layer_tree": self.layer_tree,
            "relations": self.relations,
            "polymorphic_relations": [],
            "version": "1.0",
        }

    def convert(self) -> None:
        assert self.survey_sheet
        assert self.settings_sheet
        assert self.choices_sheet

        self._settings = self._get_settings()

        self.layers.extend(self._get_choices_layers())

        display_expression = self.get_display_expression(
            self._settings["instance_name"]
        )
        layer_id = "survey_layer"
        layer_name = "Survey"
        self._enter_layer(
            generate_layer_def(
                layer_id=layer_id,
                name=layer_name,
                primary_key="uuid",
                fields=[
                    generate_uuid_field_def(),
                ],
                custom_properties={
                    "qfieldsync/cloud_action": "offline",
                    "qfieldsync/action": "offline",
                },
                display_expression=display_expression,
            )
        )

        self.build_survey_form()

    def build_survey_form(self) -> None:
        # use the top most "layer_id" from the stack to find the respective layer definition
        max_pixels: int | None = None
        geometry_type_by_layer_id: dict[str, GeometryType] = {}

        for row in self.survey_sheet:
            try:
                # If there are not `parent_ids`, it means we are at the root level
                # the form item's `parent_id` set to `None` represents that.
                layer_id = self._layer_ids[-1]
                layer_def = self.find_layer(layer_id)

                assert layer_def is not None

                if not row["type"]:
                    logger.debug(
                        f"Skipping row with empty `type` at row index {row.idx}!"
                    )

                    continue

                row_field_defs, row_form_item_defs, row_geometry_type = (
                    self._parse_form_row(row)
                )

                layer_def["fields"].extend(row_field_defs)
                layer_def["form_config"].extend(row_form_item_defs)

                # TODO find a better place for `max_pixels` logic
                if row["type"] == "image":
                    max_pixels = self._get_field_settings_max_pixels(row, max_pixels)

                if row_geometry_type:
                    if layer_id in geometry_type_by_layer_id:
                        logger.warning(
                            self.tr(
                                f"Multiple geometry types defined for layer `{layer_def['name']}`; using the first one `{row_geometry_type}`"
                            )
                        )

                        continue

                    geometry_type_by_layer_id[layer_id] = row_geometry_type

            except Exception as err:
                logger.error(
                    self.tr(
                        f"Failed to parse row with type `{row['type']}` and name `{row['name']}` at row index {row.idx}: {err}"
                    )
                )

                self.error.emit(
                    self.tr(
                        f"Failed to parse row with type `{row['type']}` and name `{row['name']}` at row index {row.idx}: {err}"
                    )
                )

                raise

        for layer_id, geometry_type in geometry_type_by_layer_id.items():
            layer_def = self.find_layer(layer_id)

            assert layer_def is not None
            assert geometry_type is not None

            layer_def["geometry_type"] = geometry_type

    def _parse_form_row(
        self, row: ParsedSheetRow
    ) -> tuple[list[FieldDef], list[FormItemDef], GeometryType | None]:
        fields = []
        form_items = []
        geometry_type = None

        widget_type_cb = self.widget_registry.get(row["type"])

        if not widget_type_cb:
            logger.info(self.tr(f"Unsupported xlsform type: {row['type']}, skipping!"))

            self.warning.emit(
                self.tr(f"Unsupported xlsform type: {row['type']}, skipping!")
            )

            return [], [], None

        # unsupported xlsform column `trigger`
        if row["trigger"]:
            self.warning.emit("Triggers are not supported yet, ignoring!")

        # we start with some defaults that are common for all field and widget types
        field_default: WeakFieldDef = self._get_field_def(row)
        form_item_default: WeakFormItemDef = {}

        if row["relevant"]:
            visibility_expr = self.get_expression(
                row["relevant"], row["name"]
            ).to_qgis()
        else:
            visibility_expr = ""

        if visibility_expr:
            form_item_default["visibility_expression"] = visibility_expr

        parsed_row = widget_type_cb(WidgetContext(self, row))
        current_container = self._current_container()

        # If the `parent_id` is `None`, it means we are at the root level
        # the form item's `parent_id` set to `None` represents that.
        if current_container is not None:
            parent_id = current_container["item_id"]
        else:
            parent_id = None

        # Determine the parent id for the current form item.
        # If `group_status` is `GroupStatus.END``, then the last parent id is popped from the stack and no new element is added.
        if parsed_row.group_status == GroupStatus.BEGIN:
            self._enter_container(
                generate_form_item_def(
                    **{
                        "type": self.get_form_group_type(),
                        **form_item_default,
                        **parsed_row.form_container,
                        "parent_id": parent_id,
                    },
                )
            )
        # alternatively, we could do call get_form recursively:
        # self.get_form(parsed_row.form_container["item_id"])
        elif parsed_row.group_status == GroupStatus.END:
            self._exit_container()

        # Determine the layer id for the current form item.
        # If `layer_status` is `layerStatus.END``, then the last layer id is popped from the stack and no new element is added.
        if parsed_row.layer_status == LayerStatus.BEGIN:
            self._enter_layer(generate_layer_def(**parsed_row.layer))
        elif parsed_row.layer_status == LayerStatus.END:
            self._exit_layer()

        if parsed_row.geometry_type:
            assert not parsed_row.layer
            assert not parsed_row.form_field
            assert not parsed_row.form_container
            assert not parsed_row.field

            geometry_type = parsed_row.geometry_type

        if parsed_row.field:
            assert not parsed_row.form_container

            field = generate_field_def(
                **{**field_default, **parsed_row.field},
            )
            fields.append(field)
            form_items.append(
                generate_form_item_def(
                    **{
                        "is_label_on_top": True,
                        **form_item_default,
                        **parsed_row.form_field,
                        "field_name": field["name"],
                        "parent_id": parent_id,
                        "type": "field",
                    },
                )
            )
        elif (
            parsed_row.form_container
            and parsed_row.group_status == GroupStatus.NONE
            and parsed_row.layer_status == LayerStatus.NONE
        ):
            self._add_container(
                generate_form_item_def(
                    **{
                        **parsed_row.form_container,
                        "parent_id": parent_id,
                    }
                )
            )

        if parsed_row.relation:
            assert parsed_row.form_field is not None
            assert parsed_row.form_field.get("type") == "relation"

            self.relations.append(
                generate_relation_def(
                    **parsed_row.relation,
                )
            )

            form_items.append(
                generate_form_item_def(
                    visibility_expression=visibility_expr,
                    is_label_on_top=True,
                    **{**form_item_default, **parsed_row.form_field},
                    parent_id=parent_id,
                )
            )

        return fields, form_items, geometry_type

    def _get_choices_values(self) -> dict[str, list[ChoicesDef]]:
        assert self.choices_sheet

        choices: dict[str, list[ChoicesDef]] = defaultdict(list)

        for idx, row in enumerate(self.choices_sheet, 1):
            last_list_name = None

            if not row["list_name"]:
                logger.debug(
                    self.tr(
                        f"Skipping row with empty `list_name` in choices at row {idx}!"
                    )
                )

                last_list_name = None

                continue

            # the choices from a single list must be consecutive values
            if last_list_name is not None and last_list_name != row["list_name"]:
                assert last_list_name not in choices

            choice_data: ChoicesDef = {
                "name": str(row["name"]).strip(),
                "label": self._get_label(row),
            }

            for col_name, col_value in row.items():
                if col_name in ("name", "label", "list_name"):
                    continue

                if not col_name:
                    logger.debug(
                        self.tr(
                            f"Empty value for `{col_name}` in choices at row {idx}, using empty string as default!"
                        )
                    )

                    continue

                choice_data[col_name] = col_value

            choices[row["list_name"]].append(choice_data)

        return dict(choices)

    def _get_choices_layers(self) -> list[LayerDef]:
        choices_layers: list[LayerDef] = []
        choice_values_by_list_name = self._get_choices_values()

        for list_name, list_choices in choice_values_by_list_name.items():
            layer_id = build_choices_layer_id(list_name)

            # The additional columns are most likely related to a single choice group,
            # so we need to iterate over all rows for the given choice group and collect the columns that are non-empty.
            columns_set = set()
            for list_choices_row in list_choices:
                for col_name, col_value in list_choices_row.items():
                    if col_name in columns_set:
                        continue

                    if col_value is None:
                        continue

                    columns_set.add(col_name)

            assert "name" in columns_set
            assert "label" in columns_set

            fields = []
            for col_name in columns_set:
                fields.append(
                    generate_field_def(
                        name=col_name,
                        type="string",
                        widget_type="TextEdit",
                    ),
                )

            cleaned_list_choices = [{"name": "", "label": ""}]
            for list_choices_row in list_choices:
                cleaned_row = {}

                for col_name in columns_set:
                    cleaned_row[col_name] = list_choices_row[col_name]

                cleaned_list_choices.append(cleaned_row)

            choices_layers.append(
                generate_layer_def(
                    layer_id=layer_id,
                    name=layer_id,
                    crs="EPSG:4326",
                    fields=fields,
                    is_private=True,
                    custom_properties={
                        "QFieldSync/cloud_action": "no_action",
                        "QFieldSync/action": "copy",
                    },
                    data=cleaned_list_choices,
                )
            )

        return choices_layers

    def get_project_extent(self, geometry_type: GeometryType, crs: str):
        if geometry_type in "NoGeometry":
            return [-9.88, 33.41, 40.97, 61.11]

        # TODO one may pass a source layer to prepopulate the geometries from, so we can compute the actual extent of those geometries
        return [-9.88, 33.41, 40.97, 61.11]

    def _get_field_settings_max_pixels(
        self, row, previous_max_pixels: int | None
    ) -> int | None:
        # the current image field does not have parameters set, return the previous value
        if not row["parameters"]:
            return previous_max_pixels

        image_max_pixels_matches = re.search(
            r"max-pixels=\s*([0-9]+)", row["parameters"], flags=re.IGNORECASE
        )

        # the current image field does not have max-pixels parameter, return the previous value
        if not image_max_pixels_matches:
            return previous_max_pixels

        image_max_pixels = int(image_max_pixels_matches.group(1))

        # the current image field has the same max-pixels parameter as the previous one, return the value
        if image_max_pixels == previous_max_pixels:
            return previous_max_pixels

        if previous_max_pixels is None:
            return image_max_pixels
        else:
            self.warning.emit(
                self.tr(
                    "Due to the presence of a mix of image attributes having max-pixels parameter of varying values, the largest max-pixels value will be applied"
                )
            )
            return max(image_max_pixels, previous_max_pixels)


def get_xlsform_type(raw_xls_type: str) -> str:
    xlsform_type, *_ = str(raw_xls_type).split(" ", 1)
    xlsform_type = xlsform_type.strip().lower()

    return xlsform_type


def build_choices_layer_id(*parts: str) -> str:
    return "_".join(["list", *parts])


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

    return ParsedRow(
        field={
            "widget_type": "TextEdit",
            **form_item,
        },
        form_field={
            "is_read_only": True,
            "show_label": True,
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


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert an XLSForm file to a QGIS project via JSON representation"
    )
    parser.add_argument(
        "input_xlsform",
        type=str,
        help="Path to the input XLSForm file",
    )
    parser.add_argument(
        "--output-json",
        type=str,
    )
    parser.add_argument(
        "--output-dir",
        type=str,
    )
    parser.add_argument(
        "--skip-failed-expressions",
        action="store_true",
        help="Whether to skip failed expressions or not; if set to true, the converter will try to convert the expression and if it fails, it will log a warning and use an empty string as the expression value; if set to false, the converter will raise an error and stop the conversion process",
    )

    args = parser.parse_args()
    output_json = xlsform_to_json(
        args.input_xlsform, skip_failed_expressions=args.skip_failed_expressions
    )

    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)

        with open(args.output_json, "w") as f:
            json.dump(output_json, f, indent=4, sort_keys=True)

    if args.output_dir:
        from json2qgis.json2qgis import ProjectCreator, ProjectDef

        output_json = cast(ProjectDef, output_json)
        creator = ProjectCreator(output_json)
        creator.build(args.output_dir)


if __name__ == "__main__":
    main()
