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

logger = logging.getLogger(__name__)

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
