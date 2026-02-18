import json
import logging
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, cast

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
)
from qgis.PyQt.QtCore import QObject, pyqtSignal

from xlsform2qgis.converter_utils import (
    build_choices_layer_id,
    get_xlsform_type,
    strip_html,
)
from xlsform2qgis.expressions.expression import (
    Expression,
    ExpressionContext,
    ParserType,
)
from xlsform2qgis.expressions.parser import ParseError
from xlsform2qgis.sheet_parser import ParsedSheet, ParsedSheetRow
from xlsform2qgis.type_defs import (
    GroupStatus,
    LayerStatus,
    XlsformSettings,
)
from xlsform2qgis.widgets import WidgetContext, WidgetRegistry

# try:
#     import markdown  # type: ignore
# except ImportError:
#     pass


logger = logging.getLogger(__name__)


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

        self._settings = self._get_settings()

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
            choices_by_list=self._get_choices_by_list(),
            survey_settings=self._settings,
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
        label = ""
        default_language = self._settings["default_language"].lower()
        if default_language:
            label_key = f"label::{default_language}"

            if sheet_row.get(label_key):
                label = strip_html(sheet_row[label_key] or "")

        if not label:
            logger.debug(
                f"Label for default language `{default_language}` not found in row index {sheet_row.idx}, falling back to `label` column!"
            )

            label = strip_html(sheet_row["label"] or "")

        return label

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
                "title": self._settings["form_title"],
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

    def _get_choices_columns(self, list_choices: list[ChoicesDef]) -> list[str]:
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

        columns_ordered = ["name", "label"] + sorted(
            col_name for col_name in columns_set if col_name not in {"name", "label"}
        )

        assert "name" in columns_set
        assert "label" in columns_set

        return columns_ordered

    def _get_choices_record(
        self, columns: list[str], raw_choice_record: ChoicesDef | None
    ) -> ChoicesDef:
        record: ChoicesDef = {}

        for column in columns:
            if raw_choice_record is None:
                if column in ("name", "label"):
                    value = ""
                else:
                    value = None
            else:
                value = raw_choice_record[column]

            record[column] = value

        return record

    def _get_choices_by_list(self) -> dict[str, list[ChoicesDef]]:
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

        cleaned_choices_by_list = {}

        for list_name, raw_choice_records in choices.items():
            columns = self._get_choices_columns(raw_choice_records)

            cleaned_choices = [
                # We always add an empty option
                self._get_choices_record(columns, None),
            ]

            for raw_choice_record in raw_choice_records:
                cleaned_row = {}

                for col_name in columns:
                    cleaned_row[col_name] = raw_choice_record[col_name]

                cleaned_choices.append(
                    self._get_choices_record(columns, raw_choice_record)
                )

            cleaned_choices_by_list[list_name] = cleaned_choices

        return cleaned_choices_by_list

    def _get_choices_layers(self) -> list[LayerDef]:
        choices_layers: list[LayerDef] = []
        choice_values_by_list_name = self._get_choices_by_list()

        for list_name, list_choices in choice_values_by_list_name.items():
            layer_id = build_choices_layer_id(list_name)

            fields = []
            for col_name in list_choices[0].keys():
                fields.append(
                    generate_field_def(
                        name=col_name,
                        type="string",
                        widget_type="TextEdit",
                    ),
                )

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
                    data=list_choices,
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
