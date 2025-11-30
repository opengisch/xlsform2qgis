from tempfile import TemporaryDirectory
import pytest
from pathlib import Path
from qgis.core import (
    Qgis,
    QgsProject,
)
from xlsform2qgis.converter import XLSFormConverter, strip_tags


class TestHTMLStripper:
    def test_strip_tags_simple(self):
        assert strip_tags("<p>Hello World</p>") == "Hello World"

    def test_strip_tags_nested(self):
        assert strip_tags("<div><p>Hello <b>World</b></p></div>") == "Hello World"

    def test_strip_tags_no_tags(self):
        assert strip_tags("Plain text") == "Plain text"

    def test_strip_tags_empty(self):
        assert strip_tags("") == ""


class TestXLSFormConverter:
    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    @pytest.fixture
    def xlsform_file(self):
        return str(Path(__file__).parent / "data/service_rating.xlsx")

    def test_init_with_invalid_file(self, xlsform_file):
        converter = XLSFormConverter("non_existent_file.xlsx")

        assert converter.xlsx_form_file == ""
        assert not converter.is_valid()

    def test_is_valid_proper_file(self, xlsform_file):
        converter = XLSFormConverter(xlsform_file)

        assert converter.xlsx_form_file == xlsform_file
        assert converter.is_valid()

    def test_converter(self, xlsform_file):
        converter = XLSFormConverter(xlsform_file)

        assert converter.xlsx_form_file == xlsform_file
        assert converter.is_valid()

        tempdir = TemporaryDirectory("test_xlsform_conversion_output", delete=False)

        converter.convert(tempdir.name)

        tempdir_path = Path(tempdir.name)
        qgz_files = list(tempdir_path.glob("*.qgz"))

        assert len(qgz_files) == 1

        project = QgsProject.instance()

        assert project.read(str(qgz_files[0]))
        assert project.crs().authid() == "EPSG:3857"

        surver_layers = project.mapLayersByName("survey")

        assert len(surver_layers) == 1

        surver_layer = surver_layers[0]

        assert surver_layer.isValid()
        assert surver_layer.geometryType() == Qgis.GeometryType.Point

        fields = surver_layer.fields()

        assert fields.names() == [
            "fid",
            "uuid",
            "recommend",
            "services",
            "info_portal_rating",
            "clinical_trials_rating",
            "support_program_rating",
            "ordering_rating",
            "rep_scheduling_rating",
            "cme_rating",
            "feature_improve",
            "part_employees",
            "full_employees",
            "employee_total",
            "employee_summary",
            "salutation",
            "name",
            "address",
            "zip_code",
            "city",
            "state",
            "comment",
        ]

        tempdir.cleanup()

    def test_convert_label_expression_simple(self, xlsform_file):
        converter = XLSFormConverter(xlsform_file)
        result = converter.convert_label_expression("${field_name}")

        assert result == """'' || "field_name" || ''"""

    def test_convert_label_expression_multiple_fields(self, xlsform_file):
        converter = XLSFormConverter(xlsform_file)
        result = converter.convert_label_expression("${field1} and ${field2}")

        assert result == """'' || "field1" || ' and ' || "field2" || ''"""

    def test_convert_expression_apostrophe_replacement(self, xlsform_file):
        converter = XLSFormConverter(xlsform_file)
        result = converter.convert_expression("it's a test")

        assert "it's a test" == result

    def test_convert_expression_selected_function(self, xlsform_file):
        converter = XLSFormConverter(xlsform_file)
        result = converter.convert_expression("selected(${field}, value)")

        assert result == '"field" =  value'

    def test_convert_expression_today_function(self, xlsform_file):
        converter = XLSFormConverter(xlsform_file)
        result = converter.convert_expression("today()")

        assert result == "format_date(now(),'yyyy-MM-dd')"
