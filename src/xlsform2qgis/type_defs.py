from enum import StrEnum
from typing import TypedDict


class GroupStatus(StrEnum):
    NONE = "none"
    BEGIN = "start"
    END = "end"


class LayerStatus(StrEnum):
    NONE = "none"
    BEGIN = "start"
    END = "end"


class XlsformSettings(TypedDict):
    form_title: str
    form_id: str
    default_language: str
    version: str
    instance_name: str
