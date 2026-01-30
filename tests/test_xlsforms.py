from pathlib import Path
import pytest
from unittest.mock import MagicMock

from xlsform2qgis.converter import extract, XLSFormConverter
from xlsform2qgis.converter_utils import (
    generate_layer_def,
    generate_field_def,
    generate_form_item_def,
)


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

    return XLSFormConverter(
        survey_sheet,
        choices_sheet,
        settings_sheet,
    )


@pytest.fixture(autouse=True)
def run_around_tests():
    # Code that runs before each test
    global survey_row_counter
    survey_row_counter = counter()
    yield


class TestConverter:
    def test_get_choices_values(self, converter: XLSFormConverter):
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
                    "type": "vector",
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
                                "id": choices_layers[0]["fields"][0]["id"],
                                "name": "name",
                                "type": "string",
                            },
                        ),
                        generate_field_def(
                            **{
                                "id": choices_layers[0]["fields"][1]["id"],
                                "name": "label",
                                "type": "string",
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
                    "type": "vector",
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
                                "id": choices_layers[1]["fields"][0]["id"],
                                "name": "name",
                                "type": "string",
                            },
                        ),
                        generate_field_def(
                            **{
                                "id": choices_layers[1]["fields"][1]["id"],
                                "name": "label",
                                "type": "string",
                            },
                        ),
                    ],
                }
            ),
        ]

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
        assert survey_layer["fields"][0] == generate_field_def(
            id=survey_layer["fields"][0]["id"],
            type="string",
            name="uuid",
            alias="UUID",
        )
        assert survey_layer["fields"][1] == generate_field_def(
            id=survey_layer["fields"][1]["id"],
            type="string",
            name="field_001",
            alias="Field 001",
            widget_type="TextEdit",
        )

        assert len(survey_layer["form_config"]) == 1
        assert survey_layer["form_config"][0] == generate_form_item_def(
            id=survey_layer["form_config"][0]["id"],
            type="field",
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
        assert survey_layer["fields"][0] == generate_field_def(
            id=survey_layer["fields"][0]["id"],
            type="string",
            name="uuid",
            alias="UUID",
        )
        assert survey_layer["fields"][1] == generate_field_def(
            id=survey_layer["fields"][1]["id"],
            type="string",
            name="field_001",
            alias="Field 001",
            widget_type="TextEdit",
        )

        assert len(survey_layer["form_config"]) == 2
        assert survey_layer["form_config"][0] == generate_form_item_def(
            id="item_container_0",
            name="Group 001",
            type="group_box",
        )
        assert survey_layer["form_config"][1] == generate_form_item_def(
            id=survey_layer["form_config"][1]["id"],
            parent_id="item_container_0",
            type="field",
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

        field_defs = converter.layers[0]["fields"]
        form_item_defs = converter.layers[0]["form_config"]

        assert len(field_defs) == 2
        assert field_defs[0] == generate_field_def(
            id=field_defs[0]["id"],
            type="string",
            name="uuid",
            alias="UUID",
        )
        assert field_defs[1] == generate_field_def(
            id=field_defs[1]["id"],
            type="string",
            name="field_001_001",
            alias="Field 001_001",
            widget_type="TextEdit",
        )

        assert len(form_item_defs) == 3
        assert form_item_defs[0] == generate_form_item_def(
            id="item_container_0",
            name="Group 001",
            type="group_box",
        )
        assert form_item_defs[1] == generate_form_item_def(
            id="item_container_1",
            name="Group 001_001",
            parent_id="item_container_0",
            type="group_box",
        )
        assert form_item_defs[2] == generate_form_item_def(
            id=form_item_defs[2]["id"],
            parent_id="item_container_1",
            type="field",
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

    @pytest.fixture
    def xlsform_filename(self):
        return str(Path(__file__).parent / "data/service_rating.xlsx")

    def test_xlsform_survey_rating_file(self, xlsform_filename: str):
        survey_sheet, choices_sheet, settings_sheet = extract(xlsform_filename)

        converter = XLSFormConverter(survey_sheet, choices_sheet, settings_sheet)

        converter.convert()

        assert len(converter.layers) == 6

        sorted_layers = sorted(converter.layers, key=lambda ml: ml["name"])

        survey_layer, *_ = sorted_layers

        assert len(survey_layer["fields"]) == 21
        assert survey_layer["fields"][0] == generate_field_def(
            id=survey_layer["fields"][0]["id"],
            type="string",
            name="uuid",
            alias="UUID",
        )
        assert survey_layer["fields"][1] == generate_field_def(
            id=survey_layer["fields"][1]["id"],
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
            id=survey_layer["fields"][2]["id"],
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
            id=survey_layer["fields"][3]["id"],
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
            id=survey_layer["fields"][4]["id"],
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
            id=survey_layer["fields"][5]["id"],
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
            id=survey_layer["fields"][6]["id"],
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
            id=survey_layer["fields"][7]["id"],
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
            id=survey_layer["fields"][8]["id"],
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
            id=survey_layer["fields"][9]["id"],
            type="string",
            name="feature_improve",
            alias="What additional digital tools or features would improve your experience?",
            widget_type="TextEdit",
            widget_config={
                "IsMultiline": True,
            },
        )
        assert survey_layer["fields"][10] == generate_field_def(
            id=survey_layer["fields"][10]["id"],
            type="integer",
            name="part_employees",
            alias="Part-time",
            widget_type="Range",
            constraint_expression='"part_employees" > 0',
            constraint_expression_description="Must have more than 1 employee",
            constraint_expression_strength="hard",
        )
        assert survey_layer["fields"][11] == generate_field_def(
            id=survey_layer["fields"][11]["id"],
            type="integer",
            name="full_employees",
            alias="Full time",
            widget_type="Range",
            constraint_expression='"full_employees" > 0',
            constraint_expression_description="Must have more than 1 employee",
            constraint_expression_strength="hard",
        )
        assert survey_layer["fields"][12] == generate_field_def(
            id=survey_layer["fields"][12]["id"],
            type="string",
            name="employee_total",
            alias="",
            widget_type="TextEdit",
            default_value='"part_employees" + "full_employees"',
            set_default_value_on_update=True,
        )
        assert survey_layer["fields"][13] == generate_field_def(
            id=survey_layer["fields"][13]["id"],
            type="boolean",
            name="employee_summary",
            alias="",
            alias_expression="'Your company is employing  a total of ' || \"employee_total\" || ' correct ?'",
            widget_type="CheckBox",
            default_value=None,
            set_default_value_on_update=False,
        )
        assert survey_layer["fields"][14] == generate_field_def(
            id=survey_layer["fields"][14]["id"],
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
            default_value=None,
            set_default_value_on_update=False,
        )
        assert survey_layer["fields"][15] == generate_field_def(
            id=survey_layer["fields"][15]["id"],
            type="string",
            name="name",
            alias="Name",
            widget_type="TextEdit",
        )
        assert survey_layer["fields"][16] == generate_field_def(
            id=survey_layer["fields"][16]["id"],
            type="string",
            name="address",
            alias="Address",
            widget_type="TextEdit",
        )
        assert survey_layer["fields"][17] == generate_field_def(
            id=survey_layer["fields"][17]["id"],
            type="string",
            name="zip_code",
            alias="Zip code",
            widget_type="TextEdit",
            constraint_expression="regexp_match(\"zip_code\", '^\\\\d{5}(-\\\\d{4})?$')",
            constraint_expression_description=None,
            constraint_expression_strength="hard",
        )
        assert survey_layer["fields"][18] == generate_field_def(
            id=survey_layer["fields"][18]["id"],
            type="string",
            name="city",
            alias="City",
            widget_type="TextEdit",
        )
        assert survey_layer["fields"][19] == generate_field_def(
            id=survey_layer["fields"][19]["id"],
            type="string",
            name="state",
            alias="State",
            widget_type="TextEdit",
        )
        assert survey_layer["fields"][20] == generate_field_def(
            id=survey_layer["fields"][20]["id"],
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
            id="item_container_0",
            name="Introduction page",
            type="group_box",
        )
        assert survey_layer["form_config"][1] == generate_form_item_def(
            id="item_container_1",
            name="Welcome to our new survey. Please answer a couple of  questions.",
            parent_id="item_container_0",
            type="group_box",
        )
        assert survey_layer["form_config"][2] == generate_form_item_def(
            id=survey_layer["form_config"][2]["id"],
            parent_id="item_container_0",
            type="field",
        )
        assert survey_layer["form_config"][3] == generate_form_item_def(
            id=survey_layer["form_config"][3]["id"],
            parent_id="item_container_0",
            type="field",
        )
        assert survey_layer["form_config"][4] == generate_form_item_def(
            id="item_container_6",
            name="Statisfaction evaluation page",
            type="group_box",
            visibility_expression="\"recommend\" = 'yes'",
        )
        assert survey_layer["form_config"][5] == generate_form_item_def(
            id="item_container_7",
            name="Services rating matrix",
            parent_id="item_container_6",
            type="group_box",
        )
        assert survey_layer["form_config"][6] == generate_form_item_def(
            id=survey_layer["form_config"][6]["id"],
            parent_id="item_container_7",
            type="field",
        )
        assert survey_layer["form_config"][7] == generate_form_item_def(
            id=survey_layer["form_config"][7]["id"],
            parent_id="item_container_7",
            type="field",
        )
        assert survey_layer["form_config"][8] == generate_form_item_def(
            id=survey_layer["form_config"][8]["id"],
            parent_id="item_container_7",
            type="field",
        )
        assert survey_layer["form_config"][9] == generate_form_item_def(
            id=survey_layer["form_config"][9]["id"],
            parent_id="item_container_7",
            type="field",
        )
        assert survey_layer["form_config"][10] == generate_form_item_def(
            id=survey_layer["form_config"][10]["id"],
            parent_id="item_container_7",
            type="field",
        )
        assert survey_layer["form_config"][11] == generate_form_item_def(
            id=survey_layer["form_config"][11]["id"],
            parent_id="item_container_7",
            type="field",
        )
        assert survey_layer["form_config"][12] == generate_form_item_def(
            id=survey_layer["form_config"][12]["id"],
            parent_id="item_container_6",
            type="field",
        )
        assert survey_layer["form_config"][13] == generate_form_item_def(
            id="item_container_17",
            name="Company details page",
            type="group_box",
        )
        assert survey_layer["form_config"][14] == generate_form_item_def(
            id="item_container_18",
            name="How many employees work in your company ?",
            parent_id="item_container_17",
            type="group_box",
        )
        assert survey_layer["form_config"][15] == generate_form_item_def(
            id=survey_layer["form_config"][15]["id"],
            parent_id="item_container_18",
            type="field",
        )
        assert survey_layer["form_config"][16] == generate_form_item_def(
            id=survey_layer["form_config"][16]["id"],
            parent_id="item_container_18",
            type="field",
        )
        assert survey_layer["form_config"][17] == generate_form_item_def(
            id=survey_layer["form_config"][17]["id"],
            parent_id="item_container_17",
            type="field",
            is_read_only=True,
            show_label=False,
        )
        assert survey_layer["form_config"][18] == generate_form_item_def(
            id=survey_layer["form_config"][18]["id"],
            parent_id="item_container_17",
            type="field",
        )
        assert survey_layer["form_config"][19] == generate_form_item_def(
            id="item_container_25",
            name="Contact details page",
            type="group_box",
        )
        assert survey_layer["form_config"][20] == generate_form_item_def(
            id="item_container_26",
            name="Please leave your contact details",
            parent_id="item_container_25",
            type="group_box",
        )
        assert survey_layer["form_config"][21] == generate_form_item_def(
            id=survey_layer["form_config"][21]["id"],
            parent_id="item_container_26",
            type="field",
        )
        assert survey_layer["form_config"][22] == generate_form_item_def(
            id=survey_layer["form_config"][22]["id"],
            parent_id="item_container_26",
            type="field",
        )
        assert survey_layer["form_config"][23] == generate_form_item_def(
            id=survey_layer["form_config"][23]["id"],
            parent_id="item_container_26",
            type="field",
        )
        assert survey_layer["form_config"][24] == generate_form_item_def(
            id=survey_layer["form_config"][24]["id"],
            parent_id="item_container_26",
            type="field",
        )
        assert survey_layer["form_config"][25] == generate_form_item_def(
            id=survey_layer["form_config"][25]["id"],
            parent_id="item_container_26",
            type="field",
        )
        assert survey_layer["form_config"][26] == generate_form_item_def(
            id=survey_layer["form_config"][26]["id"],
            parent_id="item_container_26",
            type="field",
        )
        assert survey_layer["form_config"][27] == generate_form_item_def(
            id=survey_layer["form_config"][27]["id"],
            parent_id="item_container_25",
            type="field",
        )
