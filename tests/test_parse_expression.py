from xlsform2qgis.converter import xlsform_to_qgis_expression


class TestXlsformToQgisExpression:
    def test_empty_expression(self):
        assert xlsform_to_qgis_expression("") == ""
        assert xlsform_to_qgis_expression("   ") == ""

    def test_simple_field_reference(self):
        assert xlsform_to_qgis_expression("${field}") == '"field"'
        assert xlsform_to_qgis_expression("${my_field}") == '"my_field"'

    def test_curly_quote_normalization(self):
        expression = xlsform_to_qgis_expression("'text' and 'more'")

        assert expression == "'text' and 'more'"

    def test_dot_replacement_with_field_name(self):
        assert xlsform_to_qgis_expression(". > 5", field_name="age") == '"age" > 5'
        assert xlsform_to_qgis_expression("(.) > 5", field_name="age") == '("age") > 5'
        assert (
            xlsform_to_qgis_expression(". = 10", field_name="count") == '"count" = 10'
        )

    def test_selected_function_conversion(self):
        assert (
            xlsform_to_qgis_expression("selected(${choice}, 'value')")
            == "\"choice\" = 'value'"
        )

    def test_regex_function_conversion(self):
        result = xlsform_to_qgis_expression("regex(${field}, '^[0-9]+$')")
        assert result == "regexp_match(\"field\", '^[0-9]+$')"

    def test_today_function_conversion(self):
        result = xlsform_to_qgis_expression("today()")
        assert result == "format_date(now(),'yyyy-MM-dd')"

    def test_string_length_conversion(self):
        assert (
            xlsform_to_qgis_expression("string-length(${name})") == 'length( "name" )'
        )
        assert (
            xlsform_to_qgis_expression("string-length( ${field} )")
            == 'length( "field"  )'
        )

    def test_use_current_value_without_insert(self):
        result = xlsform_to_qgis_expression("${field}", use_current_value=True)
        assert result == "current_value('field')"

    def test_use_insert_without_current_value(self):
        result = xlsform_to_qgis_expression("${field}", use_insert=True)
        assert result == '[% "field" %]'

    def test_use_insert_with_current_value(self):
        result = xlsform_to_qgis_expression(
            "${field}", use_insert=True, use_current_value=True
        )
        assert result == "[% current_value('field') %]"

    def test_calculate_expressions_substitution(self):
        calculate_exprs = {"calc_field": "10 + 5"}
        result = xlsform_to_qgis_expression(
            "${calc_field} * 2", use_insert=True, calculate_expressions=calculate_exprs
        )
        assert "[% 10 + 5 %]" in result

    def test_complex_expression(self):
        result = xlsform_to_qgis_expression("${age} > 18 and ${name} != ''")
        assert result == '"age" > 18 and "name" != \'\''

    def test_multiple_field_references(self):
        result = xlsform_to_qgis_expression("${field1} + ${field2}")
        assert result == '"field1" + "field2"'

    def test_nested_selected_functions(self):
        result = xlsform_to_qgis_expression(
            "selected(${choice1}, 'a') and selected(${choice2}, 'b')"
        )

        assert result == "\"choice1\" = 'a' and \"choice2\" = 'b'"
