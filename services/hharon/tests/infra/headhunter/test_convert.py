from typing import TYPE_CHECKING, Annotated, ClassVar

import pydantic

from hharon.infra.headhunter import (
    _convert_kwargs,  # pyright: ignore[reportPrivateUsage]
)
from hharon.pkg.hhapi.models import SavedSearchesResumesPostParameters

if TYPE_CHECKING:
    from hharon.infra.headhunter import RequestKwargs


class SampleModel(pydantic.BaseModel):
    model_config: ClassVar[pydantic.ConfigDict] = pydantic.ConfigDict(populate_by_name=True)

    field_name: Annotated[str, pydantic.Field(alias="field.name")]
    another_field: Annotated[int, pydantic.Field(alias="another.field")]


class ParamsModel(pydantic.BaseModel):
    model_config: ClassVar[pydantic.ConfigDict] = pydantic.ConfigDict(populate_by_name=True)

    param_one: Annotated[str | None, pydantic.Field(alias="param.one")] = None
    param_two: Annotated[int | None, pydantic.Field(alias="param.two")] = None


def test_original_values_are_preserved() -> None:
    expected_timeout = 10

    input_data: RequestKwargs = {
        "content": '{"content_key": "content_value"}',
        "data": {"data_key": "data_value"},
        "files": {"file_key": b"file_value"},
        "headers": {"header_key": "header_value"},
        "cookies": {"cookie_key": "cookie_value"},
        "timeout": expected_timeout,
        "extensions": {"extension_key": "extension_value"},
    }

    got = _convert_kwargs(input_data)

    assert got.get("content") == '{"content_key": "content_value"}'
    assert got.get("data") == {"data_key": "data_value"}
    assert got.get("files") == {"file_key": b"file_value"}
    assert got.get("headers") == {"header_key": "header_value"}
    assert got.get("cookies") == {"cookie_key": "cookie_value"}
    assert got.get("timeout") == expected_timeout
    assert got.get("extensions") == {"extension_key": "extension_value"}


def test_base_models_are_converted_using_aliases() -> None:
    model = SampleModel(field_name="test_value", another_field=42)

    input_data: RequestKwargs = {
        "content": model,
        "data": model,
        "json": model,
    }

    got = _convert_kwargs(input_data)

    assert got.get("content") == '{"field.name":"test_value","another.field":42}'
    assert got.get("data") == {"field.name": "test_value", "another.field": 42}
    assert got.get("json") == {"field.name": "test_value", "another.field": 42}


def test_params_as_base_model_is_converted() -> None:
    model = ParamsModel(param_one="value1", param_two=100)

    input_data: RequestKwargs = {
        "params": model,
    }

    got = _convert_kwargs(input_data)

    assert got.get("params") == {"param.one": "value1", "param.two": 100}


def test_params_original_values_are_preserved() -> None:
    input_data: RequestKwargs = {
        "params": {"key1": "value1", "key2": "value2"},
    }

    got = _convert_kwargs(input_data)

    assert got.get("params") == {"key1": "value1", "key2": "value2"}


def test_params_list_of_tuples_are_merged() -> None:
    input_data: RequestKwargs = {
        "params": [("key1", "value1"), ("key1", "value2"), ("key2", "value3")],
    }

    got = _convert_kwargs(input_data)

    assert got.get("params") == {"key1": ["value1", "value2"], "key2": ["value3"]}


def test_params_list_of_base_models_merged() -> None:

    input_data: RequestKwargs = {
        "params": [
            ParamsModel(param_one="first", param_two=1),
            ParamsModel(param_one="second", param_two=2),
            ParamsModel(param_one="third", param_two=3),
        ],
    }

    got = _convert_kwargs(input_data)

    assert got.get("params") == {"param.one": ["first", "second", "third"], "param.two": [1, 2, 3]}


def test_params_mixed_list_of_tuples_and_base_models() -> None:
    model1 = ParamsModel(param_one="model_value", param_two=10)
    model2 = ParamsModel(param_one="another_model", param_two=20)

    input_data: RequestKwargs = {  # pyright: ignore[reportAssignmentType]
        "params": [  # type: ignore[typeddict-item]
            ("tuple.key", "tuple_value1"),
            model1,
            ("tuple.key", "tuple_value2"),
            model2,
        ],
    }

    got = _convert_kwargs(input_data)

    expected = {
        "tuple.key": ["tuple_value1", "tuple_value2"],
        "param.one": ["model_value", "another_model"],
        "param.two": [10, 20],
    }
    assert got.get("params") == expected


def test_hh_models() -> None:
    got = _convert_kwargs({
        "params": [
            SavedSearchesResumesPostParameters(text="python"),
            SavedSearchesResumesPostParameters(text="javascript"),
            SavedSearchesResumesPostParameters(text_logic="AND"),
        ]
    })

    assert "params" in got
    assert isinstance(got["params"], dict)
    assert "text" in got["params"]
    assert got["params"]["text"] == ["python", "javascript"]
    assert "text.logic" in got["params"]
    assert got["params"]["text.logic"] == ["AND"]
