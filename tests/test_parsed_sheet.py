from collections.abc import Callable

from qgis.PyQt.QtCore import QVariant

import xlsform2qgis.converter as converter_module
from xlsform2qgis.converter import ParsedSheet


class _FakeQgsFields:
    def __init__(self, names: list[str | QVariant]) -> None:
        self._names = names

    def names(self) -> list[str | QVariant]:
        return self._names


class _FakeQgsFeature:
    def __init__(self, attrs: list[str | QVariant]) -> None:
        self._attrs = attrs

    def attributes(self) -> list[str | QVariant]:
        return self._attrs


class _FakeQgsVectorLayer:
    def __init__(
        self,
        names: list[str | QVariant],
        *,
        feature_count: int = 0,
        header_attrs: list[str | QVariant] | None = None,
    ) -> None:
        self._fields = _FakeQgsFields(names)
        self._feature_count = feature_count
        self._header_attrs = header_attrs or []

    def isValid(self) -> bool:
        return True

    def fields(self) -> _FakeQgsFields:
        return self._fields

    def featureCount(self) -> int:
        return self._feature_count

    def getFeature(self, _idx: int) -> _FakeQgsFeature:
        return _FakeQgsFeature(self._header_attrs)


def _patch_qgs_vector_layer(
    monkeypatch,
    factory: Callable[..., _FakeQgsVectorLayer],
) -> None:
    monkeypatch.setattr(converter_module, "QgsVectorLayer", factory)


def test_parsed_sheet_normalizes_field_names(monkeypatch) -> None:
    def factory(*_args, **_kwargs) -> _FakeQgsVectorLayer:
        return _FakeQgsVectorLayer(
            [
                " Type ",
                "Name",
                "Constraint Message",
                "label::English",
            ]
        )

    _patch_qgs_vector_layer(monkeypatch, factory)

    sheet = ParsedSheet("survey", "dummy.xlsx")

    assert sheet.indices["type"] == 0
    assert sheet.indices["name"] == 1
    assert sheet.indices["constraint_message"] == 2
    assert sheet.indices["label::english"] == 3


def test_parsed_sheet_skips_null_qvariant_headers(monkeypatch) -> None:
    def factory(*_args, **_kwargs) -> _FakeQgsVectorLayer:
        return _FakeQgsVectorLayer(["type", QVariant(), "name"])

    _patch_qgs_vector_layer(monkeypatch, factory)

    sheet = ParsedSheet("survey", "dummy.xlsx")

    assert sheet.indices["type"] == 0
    assert sheet.indices["name"] == 2
    assert sheet.indices[""] == -1


def test_parsed_sheet_normalizes_headers_from_first_feature(monkeypatch) -> None:
    def factory(*_args, **_kwargs) -> _FakeQgsVectorLayer:
        return _FakeQgsVectorLayer(
            ["Field1", "Field2"],
            feature_count=2,
            header_attrs=[" Type ", "Constraint Message", QVariant(), "Name"],
        )

    _patch_qgs_vector_layer(monkeypatch, factory)

    sheet = ParsedSheet("survey", "dummy.xlsx")

    assert sheet.skip_first_row is True
    assert sheet.indices["type"] == 0
    assert sheet.indices["constraint_message"] == 1
    assert sheet.indices["name"] == 3
