from __future__ import annotations

from enum import Enum
from typing import Annotated

import pytest
from pydantic import BaseModel, ValidationError

from nanimai_platform.utils.pydantic_enum_by_name_or_value import ByNameOrValue


class Color(Enum):
    RED = 1
    GREEN = 2
    BLUE = 3


class DTO(BaseModel):
    color: Annotated[Color, ByNameOrValue(Color)]


class TestValidateByName:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("RED", Color.RED),
            ("GREEN", Color.GREEN),
            ("BLUE", Color.BLUE),
        ],
    )
    def test_dict_returns_enum_singleton(self, name: str, expected: Color) -> None:
        assert DTO.model_validate({"color": name}).color is expected

    @pytest.mark.parametrize(
        ("json_str", "expected"),
        [
            ('{"color":"RED"}', Color.RED),
            ('{"color":"rEd"}', Color.RED),
            ('{"color":"red"}', Color.RED),
            ('{"color":"GREEN"}', Color.GREEN),
            ('{"color":"BLUE"}', Color.BLUE),
        ],
    )
    def test_json_returns_enum_singleton(self, json_str: str, expected: Color) -> None:
        assert DTO.model_validate_json(json_str).color is expected


class TestValidateByValue:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1, Color.RED),
            (2, Color.GREEN),
            (3, Color.BLUE),
        ],
    )
    def test_dict_returns_enum_singleton(self, value: int, expected: Color) -> None:
        assert DTO.model_validate({"color": value}).color is expected

    @pytest.mark.parametrize(
        ("json_str", "expected"),
        [
            ('{"color":1}', Color.RED),
            ('{"color":2}', Color.GREEN),
            ('{"color":3}', Color.BLUE),
        ],
    )
    def test_json_returns_enum_singleton(self, json_str: str, expected: Color) -> None:
        assert DTO.model_validate_json(json_str).color is expected


class TestValidatePassThrough:
    @pytest.mark.parametrize("member", list(Color))
    def test_enum_instance_is_returned_as_is(self, member: Color) -> None:
        assert DTO.model_validate({"color": member}).color is member


class TestSerialization:
    @pytest.mark.parametrize(
        ("member", "expected_name"),
        [
            (Color.RED, "red"),
            (Color.GREEN, "green"),
            (Color.BLUE, "blue"),
        ],
    )
    def test_model_dump_serializes_by_name(self, member: Color, expected_name: str) -> None:
        assert DTO(color=member).model_dump() == {"color": expected_name}

    @pytest.mark.parametrize(
        ("member", "expected_name"),
        [
            (Color.RED, "red"),
            (Color.GREEN, "green"),
            (Color.BLUE, "blue"),
        ],
    )
    def test_model_dump_json_serializes_by_name(self, member: Color, expected_name: str) -> None:
        assert DTO(color=member).model_dump_json() == f'{{"color":"{expected_name}"}}'

    def test_roundtrip_from_name(self) -> None:
        original = DTO(color=Color.RED)
        assert DTO.model_validate_json(original.model_dump_json()).color is original.color

    def test_roundtrip_from_value(self) -> None:
        restored = DTO.model_validate_json(DTO.model_validate({"color": 2}).model_dump_json())
        assert restored.color is Color.GREEN


class TestJsonSchema:
    @pytest.fixture(scope="class")
    def schema(self) -> dict[str, object]:
        return DTO.model_json_schema()

    def test_color_field_type_is_string(self, schema: dict[str, object]) -> None:
        assert schema["properties"]["color"]["type"] == "string"  # type: ignore[index] # pyright: ignore[reportIndexIssue]

    def test_color_field_title_matches_enum_class_name(self, schema: dict[str, object]) -> None:
        assert schema["properties"]["color"]["title"] == "Color"  # type: ignore[index]  # pyright: ignore[reportIndexIssue]

    def test_color_field_enum_lists_only_names(self, schema: dict[str, object]) -> None:
        assert schema["properties"]["color"]["enum"] == ["red", "green", "blue"]  # type: ignore[index]  # pyright: ignore[reportIndexIssue]

    def test_color_field_enum_contains_no_raw_values(self, schema: dict[str, object]) -> None:
        assert not any(isinstance(v, int) for v in schema["properties"]["color"]["enum"])  # type: ignore[index]  # pyright: ignore[reportIndexIssue, reportUnknownVariableType]


class TestValidationErrors:
    def test_unknown_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            _ = DTO.model_validate({"color": "YELLOW"})

    def test_unknown_name_error_lists_valid_names(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            _ = DTO.model_validate({"color": "YELLOW"})
        assert any(name in str(exc_info.value) for name in ("RED", "GREEN", "BLUE"))

    def test_unknown_value_raises(self) -> None:
        with pytest.raises(ValidationError):
            _ = DTO.model_validate({"color": 99})

    def test_dict_value_raises(self) -> None:
        with pytest.raises(ValidationError):
            _ = DTO.model_validate({"color": {"nested": "dict"}})

    def test_none_raises(self) -> None:
        with pytest.raises(ValidationError):
            _ = DTO.model_validate({"color": None})

    def test_list_raises(self) -> None:
        with pytest.raises(ValidationError):
            _ = DTO.model_validate({"color": ["RED"]})
