from enum import StrEnum

from typing import Any, Literal, TypedDict
from pathlib import Path


RelationStrength = Literal["association", "composition"]
ConstraintStrength = Literal["hard", "soft", "not_set"]
CrsDef = str


class RelationFieldPairDef(TypedDict):
    from_field: str
    to_field: str


class RelationDef(TypedDict):
    id: str
    name: str
    from_layer_id: str
    to_layer_id: str
    field_pairs: list[RelationFieldPairDef]
    strength: RelationStrength


class PolymorphicRelationDef(TypedDict):
    id: str
    name: str
    from_layer_id: str
    to_layer_field: str
    to_layer_expression: str
    to_layer_ids: str
    field_pairs: list[RelationFieldPairDef]
    strength: RelationStrength


class WeakFieldDef(TypedDict, total=False):
    field_id: str
    name: str
    type: str
    length: int
    precision: int
    comment: str

    is_not_null: bool
    is_not_null_strength: ConstraintStrength

    constraint_expression: str
    constraint_expression_description: str
    constraint_expression_strength: ConstraintStrength

    is_unique: bool
    is_unique_strength: ConstraintStrength

    default_value: str | None
    set_default_value_on_update: bool
    alias: str
    alias_expression: str
    widget_type: str
    widget_config: dict[str, Any]


class FieldDef(TypedDict):
    field_id: str
    name: str
    type: str
    length: int
    precision: int
    comment: str

    is_not_null: bool
    is_not_null_strength: ConstraintStrength

    constraint_expression: str
    constraint_expression_description: str
    constraint_expression_strength: ConstraintStrength

    is_unique: bool
    is_unique_strength: ConstraintStrength

    default_value: str | None
    set_default_value_on_update: bool
    alias: str
    alias_expression: str
    widget_type: str
    widget_config: dict[str, object]


LayerType = Literal["vector", "raster", "mesh", "vector_tile", "point_cloud"]

# class LayerType(StrEnum):
#     VECTOR = "vector"
#     RASTER = "raster"
#     MESH = "mesh"
#     VECTOR_TILE = "vector_tile"
#     POINT_CLOUD = "point_cloud"


class LayerTreeItemDef(TypedDict):
    id: str
    type: Literal["group", "layer"]
    name: str
    parent: str
    layer_id: str | None
    is_checked: bool


class VectorLayerDataprovider(StrEnum):
    GPKG = "gpkg"
    MEMORY = "memory"


class WeakFormItemDef(TypedDict, total=False):
    item_id: str
    type: Literal["field", "relation", "group_box", "tab", "row", "text"]
    # TODO rename to `label`
    name: str
    parent_id: str | None
    visibility_expression: str
    background_color: str
    is_collapsed: bool
    column_count: int
    is_markdown: bool
    show_label: bool
    is_read_only: bool


class FormItemDef(TypedDict):
    item_id: str
    type: Literal["field", "relation", "group_box", "tab", "row", "text"]
    # TODO rename to `label`
    name: str
    parent_id: str | None
    visibility_expression: str
    background_color: str
    is_collapsed: bool
    column_count: int
    is_markdown: bool
    show_label: bool
    is_read_only: bool


class WeakLayerDef(TypedDict, total=False):
    layer_id: str
    name: str
    geometry_type: Literal["Point", "LineString", "Polygon", "NoGeometry"]
    type: LayerType
    crs: CrsDef
    datasource_format: str
    fields: list[FieldDef]
    form_config: list[FormItemDef]

    is_read_only: bool
    is_identifiable: bool
    is_private: bool
    is_searchable: bool
    is_removable: bool


class LayerDef(TypedDict):
    layer_id: str
    name: str
    geometry_type: Literal["Point", "LineString", "Polygon", "NoGeometry"]
    type: LayerType
    crs: CrsDef
    datasource_format: str
    fields: list[FieldDef]
    form_config: list[FormItemDef]

    is_read_only: bool
    is_identifiable: bool
    is_private: bool
    is_searchable: bool
    is_removable: bool


class LayerTreeDef(TypedDict):
    children: list[LayerTreeItemDef]


class ProjectDef(TypedDict):
    version: str
    title: str
    author: str
    layers: list[LayerDef]
    layer_tree: LayerTreeDef

    layer_id: str
    name: str
    geometry_type: Literal["Point", "LineString", "Polygon", "NoGeometry"]
    type: LayerType
    crs: CrsDef
    datasource_format: str
    fields: list[FieldDef]
    form_config: list[FormItemDef]

    is_read_only: bool
    is_identifiable: bool
    is_private: bool
    is_searchable: bool
    is_removable: bool


class ChoicesDef(TypedDict):
    name: str
    label: str


class AliasSimpleDef(TypedDict, total=False):
    alias: str


class AliasWithExpressionDef(TypedDict, total=False):
    alias_expression: str


AliasDef = AliasSimpleDef | AliasWithExpressionDef


PathOrStr = str | Path
