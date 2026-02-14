from pathlib import Path
from unittest.mock import MagicMock

import pytest
from json2qgis.generate import (
    generate_field_def,
    generate_form_item_def,
    generate_layer_def,
)

from xlsform2qgis.converter import (
    XlsFormConverter,
    generate_uuid_field_def,
    parse_xlsform_sheets,
)
from xlsform2qgis.expressions.parser import SUPPORTED_FUNCTIONS


def format_selected_expr(field_name: str, value: str) -> str:
    expression: str = SUPPORTED_FUNCTIONS["selected"].expression  # type: ignore

    return expression.format("selected", f'"{field_name}"', f"'{value}'")


def counter():
    global_counter = 0
    while True:
        yield global_counter
        global_counter += 1


survey_row_counter = counter()


def generate_survey_row(**kwargs):
    return {
        "idx": next(survey_row_counter),
        "type": "",
        "name": "",
        "label": "",
        "calculation": "",
        "relevant": "",
        "choice_filter": "",
        "parameters": "",
        "constraint": "",
        "constraint_message": "",
        "required": "",
        "default": "",
        "is_read_only": "",
        "trigger": "",
        "appearance": "",
        **kwargs,
    }


@pytest.fixture
def converter():
    survey_sheet = MagicMock()
    choices_sheet = MagicMock()
    settings_sheet = MagicMock()

    return XlsFormConverter(
        survey_sheet,
        choices_sheet,
        settings_sheet,
        root_form_group_type="group_box",
    )


@pytest.fixture(autouse=True)
def run_around_tests():
    # Code that runs before each test
    global survey_row_counter
    survey_row_counter = counter()
    yield


class TestConverter:
    def test_get_choices_values(self, converter: XlsFormConverter):
        converter.choices_sheet.__iter__.return_value = [  # type: ignore
            {
                "list_name": "list_001",
                "name": "value_001_001",
                "label": "label_001_001",
            },
            {
                "list_name": "list_001",
                "name": "value_001_002",
                "label": "label_001_002",
            },
            {
                "list_name": "list_002",
                "name": "value_002_001",
                "label": "label_002_001",
            },
        ]

        choices_values = converter._get_choices_values()

        assert choices_values == {
            "list_001": [
                {
                    "name": "",
                    "label": "",
                },
                {
                    "name": "value_001_001",
                    "label": "label_001_001",
                },
                {
                    "name": "value_001_002",
                    "label": "label_001_002",
                },
            ],
            "list_002": [
                {
                    "name": "",
                    "label": "",
                },
                {
                    "name": "value_002_001",
                    "label": "label_002_001",
                },
            ],
        }

    def test_get_choices_layers(self, converter):
        converter.choices_sheet.__iter__.return_value = [
            {
                "list_name": "list_001",
                "name": "value_001_001",
                "label": "label_001_001",
            },
            {
                "list_name": "list_001",
                "name": "value_001_002",
                "label": "label_001_002",
            },
            {
                "list_name": "list_002",
                "name": "value_002_001",
                "label": "label_002_001",
            },
        ]

        choices_values = converter._get_choices_values()
        choices_layers = converter._get_choices_layers()

        assert choices_layers == [
            generate_layer_def(
                **{
                    "name": "list_list_001",
                    "layer_id": choices_layers[0]["layer_id"],
                    "geometry_type": "NoGeometry",
                    "layer_type": "vector",
                    "crs": "EPSG:4326",
                    "custom_properties": {
                        "QFieldSync/action": "copy",
                        "QFieldSync/cloud_action": "no_action",
                    },
                    "is_private": True,
                    "data": choices_values.get("list_001", []),
                    "fields": [
                        generate_field_def(
                            **{
                                "field_id": choices_layers[0]["fields"][0]["field_id"],
                                "name": "name",
                                "type": "string",
                                "widget_type": "TextEdit",
                            },
                        ),
                        generate_field_def(
                            **{
                                "field_id": choices_layers[0]["fields"][1]["field_id"],
                                "name": "label",
                                "type": "string",
                                "widget_type": "TextEdit",
                            },
                        ),
                    ],
                }
            ),
            generate_layer_def(
                **{
                    "name": "list_list_002",
                    "layer_id": choices_layers[1]["layer_id"],
                    "geometry_type": "NoGeometry",
                    "layer_type": "vector",
                    "crs": "EPSG:4326",
                    "custom_properties": {
                        "QFieldSync/action": "copy",
                        "QFieldSync/cloud_action": "no_action",
                    },
                    "is_private": True,
                    "data": choices_values.get("list_002", []),
                    "fields": [
                        generate_field_def(
                            **{
                                "field_id": choices_layers[1]["fields"][0]["field_id"],
                                "name": "name",
                                "type": "string",
                                "widget_type": "TextEdit",
                            },
                        ),
                        generate_field_def(
                            **{
                                "field_id": choices_layers[1]["fields"][1]["field_id"],
                                "name": "label",
                                "type": "string",
                                "widget_type": "TextEdit",
                            },
                        ),
                    ],
                }
            ),
        ]

    def test_xlsform_form_group_type_default(self):
        survey_sheet = MagicMock()
        choices_sheet = MagicMock()
        settings_sheet = MagicMock()

        converter = XlsFormConverter(survey_sheet, choices_sheet, settings_sheet)

        assert converter._form_group_type == "group_box"
        assert converter._root_form_group_type == "tab"
        assert converter.get_form_group_type() == "tab"

        # simulate there is a new group in the survey sheet

        converter.parent_ids.append("parent_id_here")

        assert converter.get_form_group_type() == "group_box"

    def test_xlsform_form_group_type_configured(self):
        survey_sheet = MagicMock()
        choices_sheet = MagicMock()
        settings_sheet = MagicMock()

        converter = XlsFormConverter(
            survey_sheet,
            choices_sheet,
            settings_sheet,
            form_group_type="tab",
            root_form_group_type="group_box",
        )

        assert converter._form_group_type == "tab"
        assert converter._root_form_group_type == "group_box"
        assert converter.get_form_group_type() == "group_box"

        # simulate there is a new group in the survey sheet
        converter.parent_ids.append("parent_id_here")

        assert converter.get_form_group_type() == "tab"

    def test_xlsform_with_text_field(self, converter):
        converter.survey_sheet.__iter__.return_value = [
            generate_survey_row(
                type="text",
                name="field_001",
                label="Field 001",
            )
        ]

        converter.convert()

        assert len(converter.layers) == 1

        survey_layer = converter.layers[0]

        assert len(survey_layer["fields"]) == 2
        assert survey_layer["fields"][0] == generate_uuid_field_def(
            field_id=survey_layer["fields"][0]["field_id"],
        )
        assert survey_layer["fields"][1] == generate_field_def(
            field_id=survey_layer["fields"][1]["field_id"],
            type="string",
            name="field_001",
            alias="Field 001",
            widget_type="TextEdit",
        )

        assert len(survey_layer["form_config"]) == 1
        assert survey_layer["form_config"][0] == generate_form_item_def(
            item_id=survey_layer["form_config"][0]["item_id"],
            field_name="field_001",
            type="field",
            is_label_on_top=True,
        )

    def test_xlsform_label(self, converter):
        converter.survey_sheet.__iter__.return_value = [
            generate_survey_row(
                type="text",
                name="field_001",
            ),
            generate_survey_row(
                type="text",
                name="field_002",
                label="Field 002",
            ),
            generate_survey_row(
                **{
                    "type": "text",
                    "name": "field_003",
                    "label": "Field 003",
                    "label::english": "Field English 003",
                }
            ),
        ]
        converter.settings_sheet.__iter__.return_value = [
            {"default_language": "English"}
        ]

        converter.convert()

        assert len(converter.layers) == 1

        survey_layer = converter.layers[0]

        assert len(survey_layer["fields"]) == 4

        assert survey_layer["fields"][0] == generate_uuid_field_def(
            field_id=survey_layer["fields"][0]["field_id"],
        )
        assert survey_layer["fields"][1] == generate_field_def(
            field_id=survey_layer["fields"][1]["field_id"],
            type="string",
            name="field_001",
            widget_type="TextEdit",
        )
        assert survey_layer["fields"][2] == generate_field_def(
            field_id=survey_layer["fields"][2]["field_id"],
            type="string",
            name="field_002",
            alias="Field 002",
            widget_type="TextEdit",
        )
        assert survey_layer["fields"][3] == generate_field_def(
            field_id=survey_layer["fields"][3]["field_id"],
            type="string",
            name="field_003",
            alias="Field English 003",
            widget_type="TextEdit",
        )

    def test_xlsform_with_group(self, converter):
        converter.survey_sheet.__iter__.return_value = [
            generate_survey_row(
                type="begin group",
                name="group_001",
                label="Group 001",
            ),
            generate_survey_row(
                type="text",
                name="field_001",
                label="Field 001",
            ),
            generate_survey_row(
                type="end group",
            ),
        ]

        converter.convert()

        assert len(converter.layers) == 1

        survey_layer = converter.layers[0]

        assert len(survey_layer["fields"]) == 2
        assert survey_layer["fields"][0] == generate_uuid_field_def(
            field_id=survey_layer["fields"][0]["field_id"],
        )
        assert survey_layer["fields"][1] == generate_field_def(
            field_id=survey_layer["fields"][1]["field_id"],
            type="string",
            name="field_001",
            alias="Field 001",
            widget_type="TextEdit",
        )

        assert len(survey_layer["form_config"]) == 2
        assert survey_layer["form_config"][0] == generate_form_item_def(
            item_id="item_container_0",
            label="Group 001",
            type="group_box",
        )
        assert survey_layer["form_config"][1] == generate_form_item_def(
            item_id=survey_layer["form_config"][1]["item_id"],
            field_name="field_001",
            parent_id="item_container_0",
            type="field",
            is_label_on_top=True,
        )

    def test_xlsform_with_group_nesting(self, converter):
        converter.survey_sheet.__iter__.return_value = [
            generate_survey_row(
                type="begin group",
                name="group_001",
                label="Group 001",
            ),
            generate_survey_row(
                type="begin group",
                name="group_001_001",
                label="Group 001_001",
            ),
            generate_survey_row(
                type="text",
                name="field_001_001",
                label="Field 001_001",
            ),
            generate_survey_row(
                type="end group",
            ),
            generate_survey_row(
                type="end group",
            ),
        ]

        converter.convert()

        assert len(converter.layers) == 1

        survey_layer = converter.layers[0]

        assert len(survey_layer["fields"]) == 2
        assert survey_layer["fields"][0] == generate_uuid_field_def(
            field_id=survey_layer["fields"][0]["field_id"],
        )
        assert survey_layer["fields"][1] == generate_field_def(
            field_id=survey_layer["fields"][1]["field_id"],
            type="string",
            name="field_001_001",
            alias="Field 001_001",
            widget_type="TextEdit",
        )

        assert len(survey_layer["form_config"]) == 3
        assert survey_layer["form_config"][0] == generate_form_item_def(
            item_id="item_container_0",
            label="Group 001",
            type="group_box",
        )
        assert survey_layer["form_config"][1] == generate_form_item_def(
            item_id="item_container_1",
            label="Group 001_001",
            parent_id="item_container_0",
            type="group_box",
        )
        assert survey_layer["form_config"][2] == generate_form_item_def(
            item_id=survey_layer["form_config"][2]["item_id"],
            field_name="field_001_001",
            parent_id="item_container_1",
            type="field",
            is_label_on_top=True,
        )

    def test_xlsform_with_repeat(self, converter):
        converter.survey_sheet.__iter__.return_value = [
            generate_survey_row(
                type="begin repeat",
                name="group_001",
                label="Group 001",
            ),
            generate_survey_row(
                type="begin group",
                name="group_001_001",
                label="Group 001_001",
            ),
            generate_survey_row(
                type="text",
                name="field_001",
                label="Field 001",
            ),
            generate_survey_row(
                type="end group",
            ),
            generate_survey_row(
                type="end repeat",
            ),
            generate_survey_row(
                type="integer",
                name="field_002",
                label="Field 002",
            ),
        ]

        converter.convert()

        assert len(converter.layers) == 2

        survey_layer, repeat_layer_1 = converter.layers

        assert survey_layer["layer_id"] == "survey_layer"
        assert len(survey_layer["fields"]) == 2
        assert survey_layer["fields"][0]["name"] == "uuid"
        assert survey_layer["fields"][1]["name"] == "field_002"
        assert len(repeat_layer_1["fields"]) == 3
        assert repeat_layer_1["fields"][0]["name"] == "uuid"
        assert repeat_layer_1["fields"][1]["name"] == "uuid_parent"
        assert repeat_layer_1["fields"][2]["name"] == "field_001"

    def test_xlsform_geometry(self, converter):
        converter.survey_sheet.__iter__.return_value = [
            generate_survey_row(
                type="start-geoshape",
                name="start-geoshape_001",
            ),
        ]

        converter.convert()

        assert len(converter.layers) == 1

        survey_layer = converter.layers[0]

        assert survey_layer["geometry_type"] == "Polygon"

    def test_xlsform_display_expression(self, converter):
        converter.settings_sheet.__iter__.return_value = [
            {"instance_name": r"concat(${lname}, '-', ${fname}, '-', uuid())"},
        ]

        converter.convert()

        assert converter._settings
        assert (
            converter._settings["instance_name"]
            == r"concat(${lname}, '-', ${fname}, '-', uuid())"
        )
        assert (
            converter.get_display_expression(converter._settings["instance_name"])
            == "concat(\"lname\", '-', \"fname\", '-', uuid(format:='WithoutBraces')))"
        )

    @pytest.fixture
    def xlsform_filename(self):
        return str(Path(__file__).parent / "data/service_rating.xlsx")

    def test_xlsform_survey_rating_file(self, xlsform_filename: str):
        survey_sheet, choices_sheet, settings_sheet = parse_xlsform_sheets(
            xlsform_filename
        )

        converter = XlsFormConverter(
            survey_sheet, choices_sheet, settings_sheet, root_form_group_type="tab"
        )

        converter.convert()

        assert len(converter.layers) == 6

        sorted_layers = sorted(converter.layers, key=lambda ml: ml["name"])

        survey_layer, *_ = sorted_layers

        assert len(survey_layer["fields"]) == 21
        assert survey_layer["fields"][0] == generate_uuid_field_def(
            field_id=survey_layer["fields"][0]["field_id"],
        )
        assert survey_layer["fields"][1] == generate_field_def(
            field_id=survey_layer["fields"][1]["field_id"],
            type="string",
            name="recommend",
            alias="Would you recommend our services ?",
            widget_type="ValueRelation",
            widget_config={
                "AllowMulti": False,
                "AllowNull": False,
                "FilterExpression": "",
                "Key": "name",
                "Layer": "list_yes_no",
                "LayerName": "yes_no",
                "Value": "label",
            },
            is_not_null=True,
            is_not_null_strength="hard",
        )
        assert survey_layer["fields"][2] == generate_field_def(
            field_id=survey_layer["fields"][2]["field_id"],
            type="string",
            name="services",
            alias="Which services are you using ?",
            widget_type="ValueRelation",
            widget_config={
                "AllowMulti": True,
                "AllowNull": False,
                "FilterExpression": " \"name\" != '' ",
                "Key": "name",
                "Layer": "list_services",
                "LayerName": "services",
                "Value": "label",
            },
            is_not_null=True,
            is_not_null_strength="hard",
        )
        assert survey_layer["fields"][3] == generate_field_def(
            field_id=survey_layer["fields"][3]["field_id"],
            type="string",
            name="info_portal_rating",
            alias="Medication information portal",
            widget_type="ValueRelation",
            widget_config={
                "AllowMulti": False,
                "AllowNull": False,
                "FilterExpression": "",
                "Key": "name",
                "Layer": "list_rating",
                "LayerName": "rating",
                "Value": "label",
            },
            is_not_null=False,
            is_not_null_strength="not_set",
        )
        assert survey_layer["fields"][4] == generate_field_def(
            field_id=survey_layer["fields"][4]["field_id"],
            type="string",
            name="clinical_trials_rating",
            alias="Clinical trials information",
            widget_type="ValueRelation",
            widget_config={
                "AllowMulti": False,
                "AllowNull": False,
                "FilterExpression": "",
                "Key": "name",
                "Layer": "list_rating",
                "LayerName": "rating",
                "Value": "label",
            },
            is_not_null=False,
            is_not_null_strength="not_set",
        )
        assert survey_layer["fields"][5] == generate_field_def(
            field_id=survey_layer["fields"][5]["field_id"],
            type="string",
            name="support_program_rating",
            alias="Patient support program portal",
            widget_type="ValueRelation",
            widget_config={
                "AllowMulti": False,
                "AllowNull": False,
                "FilterExpression": "",
                "Key": "name",
                "Layer": "list_rating",
                "LayerName": "rating",
                "Value": "label",
            },
            is_not_null=False,
            is_not_null_strength="not_set",
        )
        assert survey_layer["fields"][6] == generate_field_def(
            field_id=survey_layer["fields"][6]["field_id"],
            type="string",
            name="ordering_rating",
            alias="E-sampling or ordering platform",
            widget_type="ValueRelation",
            widget_config={
                "AllowMulti": False,
                "AllowNull": False,
                "FilterExpression": "",
                "Key": "name",
                "Layer": "list_rating",
                "LayerName": "rating",
                "Value": "label",
            },
            is_not_null=False,
            is_not_null_strength="not_set",
        )
        assert survey_layer["fields"][7] == generate_field_def(
            field_id=survey_layer["fields"][7]["field_id"],
            type="string",
            name="rep_scheduling_rating",
            alias="Medical representative scheduling",
            widget_type="ValueRelation",
            widget_config={
                "AllowMulti": False,
                "AllowNull": False,
                "FilterExpression": "",
                "Key": "name",
                "Layer": "list_rating",
                "LayerName": "rating",
                "Value": "label",
            },
            is_not_null=False,
            is_not_null_strength="not_set",
        )
        assert survey_layer["fields"][8] == generate_field_def(
            field_id=survey_layer["fields"][8]["field_id"],
            type="string",
            name="cme_rating",
            alias="Continuing Medical Education (CME) platform",
            widget_type="ValueRelation",
            widget_config={
                "AllowMulti": False,
                "AllowNull": False,
                "FilterExpression": "",
                "Key": "name",
                "Layer": "list_rating",
                "LayerName": "rating",
                "Value": "label",
            },
            is_not_null=False,
            is_not_null_strength="not_set",
        )
        assert survey_layer["fields"][9] == generate_field_def(
            field_id=survey_layer["fields"][9]["field_id"],
            type="string",
            name="feature_improve",
            alias="What additional digital tools or features would improve your experience?",
            widget_type="TextEdit",
            widget_config={
                "IsMultiline": True,
            },
        )
        assert survey_layer["fields"][10] == generate_field_def(
            field_id=survey_layer["fields"][10]["field_id"],
            type="integer",
            name="part_employees",
            alias="Part-time",
            widget_type="Range",
            constraint_expression='"part_employees" > 0',
            constraint_expression_description="Must have more than 1 employee",
            constraint_expression_strength="hard",
        )
        assert survey_layer["fields"][11] == generate_field_def(
            field_id=survey_layer["fields"][11]["field_id"],
            type="integer",
            name="full_employees",
            alias="Full time",
            widget_type="Range",
            constraint_expression='"full_employees" > 0',
            constraint_expression_description="Must have more than 1 employee",
            constraint_expression_strength="hard",
        )
        assert survey_layer["fields"][12] == generate_field_def(
            field_id=survey_layer["fields"][12]["field_id"],
            type="string",
            name="employee_total",
            alias="",
            widget_type="TextEdit",
            default_value='"part_employees" + "full_employees"',
            set_default_value_on_update=True,
        )
        assert survey_layer["fields"][13] == generate_field_def(
            field_id=survey_layer["fields"][13]["field_id"],
            type="boolean",
            name="employee_summary",
            alias="",
            alias_expression="'Your company is employing  a total of ' || \"employee_total\" || ' correct ?'",
            widget_type="CheckBox",
            default_value="",
            set_default_value_on_update=False,
        )
        assert survey_layer["fields"][14] == generate_field_def(
            field_id=survey_layer["fields"][14]["field_id"],
            type="string",
            name="salutation",
            alias="Salutation",
            widget_type="ValueRelation",
            widget_config={
                "AllowMulti": False,
                "AllowNull": False,
                "FilterExpression": "",
                "Key": "name",
                "Layer": "list_salutation",
                "LayerName": "salutation",
                "Value": "label",
            },
            default_value="",
            set_default_value_on_update=False,
        )
        assert survey_layer["fields"][15] == generate_field_def(
            field_id=survey_layer["fields"][15]["field_id"],
            type="string",
            name="name",
            alias="Name",
            widget_type="TextEdit",
        )
        assert survey_layer["fields"][16] == generate_field_def(
            field_id=survey_layer["fields"][16]["field_id"],
            type="string",
            name="address",
            alias="Address",
            widget_type="TextEdit",
        )
        assert survey_layer["fields"][17] == generate_field_def(
            field_id=survey_layer["fields"][17]["field_id"],
            type="string",
            name="zip_code",
            alias="Zip code",
            widget_type="TextEdit",
            constraint_expression="regexp_match(\"zip_code\", '^\\d{5}(-\\d{4})?$')",
            constraint_expression_description="",
            constraint_expression_strength="hard",
        )
        assert survey_layer["fields"][18] == generate_field_def(
            field_id=survey_layer["fields"][18]["field_id"],
            type="string",
            name="city",
            alias="City",
            widget_type="TextEdit",
        )
        assert survey_layer["fields"][19] == generate_field_def(
            field_id=survey_layer["fields"][19]["field_id"],
            type="string",
            name="state",
            alias="State",
            widget_type="TextEdit",
        )
        assert survey_layer["fields"][20] == generate_field_def(
            field_id=survey_layer["fields"][20]["field_id"],
            type="string",
            name="comment",
            alias="Would you like to leave a last comment ?",
            widget_type="TextEdit",
            widget_config={
                "IsMultiline": True,
            },
        )

        assert len(survey_layer["form_config"]) == 28
        assert survey_layer["form_config"][0] == generate_form_item_def(
            item_id="item_container_0",
            label="Introduction page",
            type="tab",
        )
        assert survey_layer["form_config"][1] == generate_form_item_def(
            item_id="item_container_1",
            label="Welcome to our new survey. Please answer a couple of  questions.",
            parent_id="item_container_0",
            type="text",
            is_markdown=False,
        )
        assert survey_layer["form_config"][2] == generate_form_item_def(
            item_id=survey_layer["form_config"][2]["item_id"],
            field_name="recommend",
            parent_id="item_container_0",
            type="field",
        )
        assert survey_layer["form_config"][3] == generate_form_item_def(
            item_id=survey_layer["form_config"][3]["item_id"],
            field_name="services",
            parent_id="item_container_0",
            type="field",
            visibility_expression=format_selected_expr("recommend", "yes"),
        )
        assert survey_layer["form_config"][4] == generate_form_item_def(
            item_id="item_container_6",
            label="Statisfaction evaluation page",
            type="tab",
            visibility_expression=format_selected_expr("recommend", "yes"),
        )
        assert survey_layer["form_config"][5] == generate_form_item_def(
            item_id="item_container_7",
            label="Services rating matrix",
            parent_id="item_container_6",
            type="group_box",
        )
        assert survey_layer["form_config"][6] == generate_form_item_def(
            item_id=survey_layer["form_config"][6]["item_id"],
            field_name="info_portal_rating",
            parent_id="item_container_7",
            type="field",
        )
        assert survey_layer["form_config"][7] == generate_form_item_def(
            item_id=survey_layer["form_config"][7]["item_id"],
            field_name="clinical_trials_rating",
            parent_id="item_container_7",
            type="field",
        )
        assert survey_layer["form_config"][8] == generate_form_item_def(
            item_id=survey_layer["form_config"][8]["item_id"],
            field_name="support_program_rating",
            parent_id="item_container_7",
            type="field",
            visibility_expression=format_selected_expr("services", "support_program"),
        )
        assert survey_layer["form_config"][9] == generate_form_item_def(
            item_id=survey_layer["form_config"][9]["item_id"],
            field_name="ordering_rating",
            parent_id="item_container_7",
            type="field",
            visibility_expression=format_selected_expr("services", "ordering"),
        )
        assert survey_layer["form_config"][10] == generate_form_item_def(
            item_id=survey_layer["form_config"][10]["item_id"],
            field_name="rep_scheduling_rating",
            parent_id="item_container_7",
            type="field",
        )
        assert survey_layer["form_config"][11] == generate_form_item_def(
            item_id=survey_layer["form_config"][11]["item_id"],
            field_name="cme_rating",
            parent_id="item_container_7",
            type="field",
        )
        assert survey_layer["form_config"][12] == generate_form_item_def(
            item_id=survey_layer["form_config"][12]["item_id"],
            field_name="feature_improve",
            parent_id="item_container_6",
            type="field",
        )
        assert survey_layer["form_config"][13] == generate_form_item_def(
            item_id="item_container_17",
            label="Company details page",
            type="tab",
        )
        assert survey_layer["form_config"][14] == generate_form_item_def(
            item_id="item_container_18",
            label="How many employees work in your company ?",
            parent_id="item_container_17",
            type="group_box",
        )
        assert survey_layer["form_config"][15] == generate_form_item_def(
            item_id=survey_layer["form_config"][15]["item_id"],
            field_name="part_employees",
            parent_id="item_container_18",
            type="field",
        )
        assert survey_layer["form_config"][16] == generate_form_item_def(
            item_id=survey_layer["form_config"][16]["item_id"],
            field_name="full_employees",
            parent_id="item_container_18",
            type="field",
        )
        assert survey_layer["form_config"][17] == generate_form_item_def(
            item_id=survey_layer["form_config"][17]["item_id"],
            field_name="employee_total",
            parent_id="item_container_17",
            type="field",
            is_read_only=True,
            show_label=False,
        )
        assert survey_layer["form_config"][18] == generate_form_item_def(
            item_id=survey_layer["form_config"][18]["item_id"],
            field_name="employee_summary",
            parent_id="item_container_17",
            type="field",
            visibility_expression='"part_employees" > 1 and "full_employees" > 1',
        )
        assert survey_layer["form_config"][19] == generate_form_item_def(
            item_id="item_container_25",
            label="Contact details page",
            type="tab",
        )
        assert survey_layer["form_config"][20] == generate_form_item_def(
            item_id="item_container_26",
            label="Please leave your contact details",
            parent_id="item_container_25",
            type="group_box",
        )
        assert survey_layer["form_config"][21] == generate_form_item_def(
            item_id=survey_layer["form_config"][21]["item_id"],
            field_name="salutation",
            parent_id="item_container_26",
            type="field",
        )
        assert survey_layer["form_config"][22] == generate_form_item_def(
            item_id=survey_layer["form_config"][22]["item_id"],
            field_name="name",
            parent_id="item_container_26",
            type="field",
        )
        assert survey_layer["form_config"][23] == generate_form_item_def(
            item_id=survey_layer["form_config"][23]["item_id"],
            field_name="address",
            parent_id="item_container_26",
            type="field",
        )
        assert survey_layer["form_config"][24] == generate_form_item_def(
            item_id=survey_layer["form_config"][24]["item_id"],
            field_name="zip_code",
            parent_id="item_container_26",
            type="field",
        )
        assert survey_layer["form_config"][25] == generate_form_item_def(
            item_id=survey_layer["form_config"][25]["item_id"],
            field_name="city",
            parent_id="item_container_26",
            type="field",
        )
        assert survey_layer["form_config"][26] == generate_form_item_def(
            item_id=survey_layer["form_config"][26]["item_id"],
            field_name="state",
            parent_id="item_container_26",
            type="field",
        )
        assert survey_layer["form_config"][27] == generate_form_item_def(
            item_id=survey_layer["form_config"][27]["item_id"],
            field_name="comment",
            parent_id="item_container_25",
            type="field",
        )
