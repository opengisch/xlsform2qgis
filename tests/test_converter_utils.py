from xlsform2qgis.converter_utils import (
    HTMLStripper,
    parse_xlsform_range_parameters,
    parse_xlsform_select_from_file_parameters,
    strip_html,
)


class TestHTMLStripper:
    def test_handle_data_and_get_data(self) -> None:
        stripper = HTMLStripper()
        stripper.handle_data("Hello")
        stripper.handle_data(" ")
        stripper.handle_data("World")

        assert stripper.get_data() == "Hello World"

    def test_strip_html_simple(self) -> None:
        assert strip_html("<p>Hello World</p>") == "Hello World"

    def test_strip_html_nested(self) -> None:
        assert strip_html("<div><p>Hello <b>World</b></p></div>") == "Hello World"

    def test_strip_html_no_tags(self) -> None:
        assert strip_html("Plain text") == "Plain text"

    def test_strip_html_empty(self) -> None:
        assert strip_html("") == ""


class TestParseXlsformRangeParameters:
    def test_all_parameters_present(self) -> None:
        start, end, step = parse_xlsform_range_parameters("start=1 end=20 step=3")

        assert (start, end, step) == (1.0, 20.0, 3.0)

    def test_defaults_when_missing(self) -> None:
        start, end, step = parse_xlsform_range_parameters("")

        assert (start, end, step) == (0.0, 10.0, 1.0)

    def test_partial_parameters(self) -> None:
        start, end, step = parse_xlsform_range_parameters("end=42")

        assert (start, end, step) == (0.0, 42.0, 1.0)

    def test_case_insensitive_keys(self) -> None:
        start, end, step = parse_xlsform_range_parameters("StArT=2 EnD=8 StEp=2")

        assert (start, end, step) == (2.0, 8.0, 2.0)


class TestParseXlsformSelectFromFileParameters:
    def test_all_parameters_present(self) -> None:
        key, value = parse_xlsform_select_from_file_parameters(
            "value=uuid label=display_name"
        )

        assert (key, value) == ("uuid", "display_name")

    def test_defaults_when_missing(self) -> None:
        key, value = parse_xlsform_select_from_file_parameters("")

        assert (key, value) == ("name", "label")

    def test_partial_parameters(self) -> None:
        key, value = parse_xlsform_select_from_file_parameters("value=my_id")

        assert (key, value) == ("my_id", "label")

    def test_whitespace_around_equal(self) -> None:
        key, value = parse_xlsform_select_from_file_parameters(
            "value = custom_id label   = custom_label"
        )

        assert (key, value) == ("custom_id", "custom_label")
