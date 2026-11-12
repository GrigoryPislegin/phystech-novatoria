from collections.abc import Callable
from typing import Any, final
from uuid import uuid4

import pytest
from pydantic import UUID4, BaseModel, Field

from hharon.utils.serialization import (
    DeserializationError,
    SerializationError,
    deserialize,
    serialize,
)


class Nested(BaseModel):
    a: int


class Box1(BaseModel):
    b: int
    c: Nested


class Box2(BaseModel):
    d: UUID4


STATIC_ID = uuid4()


class NestedRequired(BaseModel):
    required_field: str


class ModelWithRequired(BaseModel):
    nested: NestedRequired


class ModelWithConstraints(BaseModel):
    positive_number: int = Field(gt=0)


@final
class BrokenSerializable:
    def __init__(self):
        self.data = object()  # Object that can't be JSON serialized


def broken_serializer(value: Any) -> bytes:  # pyright: ignore[reportExplicitAny, reportAny, reportUnusedParameter]  # noqa: ARG001
    raise ValueError("Serialization failed in custom serializer")


def broken_deserializer(value: bytes) -> Any:  # pyright: ignore[reportExplicitAny, reportUnusedParameter, reportAny]  # noqa: ARG001
    raise ValueError("Deserialization failed in custom deserializer")


circular_list = []
circular_list.append(circular_list)


@pytest.mark.parametrize(
    ("value", "using", "expected"),
    [
        ("123", str.encode, b"123"),
        (321, None, b"321"),
        (Box1(b=5, c=Nested(a=10)), None, b'{"b":5,"c":{"a":10}}'),
        (Box2(d=STATIC_ID), None, b'{"d":"' + str(STATIC_ID).encode() + b'"}'),
        ({"e": True, "b": None}, None, b'{"e":true,"b":null}'),
    ],
)
def test_serialize[T](value: T, using: Callable[[T], bytes] | None, expected: bytes):
    if using is None:
        assert serialize(value) == expected
    else:
        assert serialize(value, using=using) == expected


@pytest.mark.parametrize(
    ("value", "using", "to", "expected"),
    [
        (b"123", bytes.decode, None, "123"),
        (b"321", None, int, 321),
        (b'{"b":5,"c":{"a":10}}', None, Box1, Box1(b=5, c=Nested(a=10))),
        (b'{"d":"' + str(STATIC_ID).encode() + b'"}', None, Box2, Box2(d=STATIC_ID)),
        (b'{"e":true}', None, dict[str, bool], {"e": True}),
    ],
)
def test_deserialize[T](value: bytes, using: Callable[[bytes], T] | None, to: type[T] | None, expected: T):
    if to is not None:
        assert deserialize(value, to=to) == expected
    elif using is not None:
        assert deserialize(value, using=using) == expected
    else:
        pytest.fail("Either using or to must be provided")


@pytest.mark.parametrize(
    ("value", "serializer", "deserializer"),
    [
        ("hello world", str.encode, bytes.decode),
        (312, None, None),
        (123, int.to_bytes, int.from_bytes),
        ({"b": 5, "c": {"a": 10}}, None, None),
        (Box1(b=5, c=Nested(a=10)), None, None),
        (Box2(d=STATIC_ID), None, None),
        ([123, 321, 123], None, None),
        ({123, 456, 789}, None, None),
    ],
)
def test_roundtrip[T](value: T, serializer: Callable[[T], bytes] | None, deserializer: Callable[[bytes], T] | None):
    if serializer is not None:
        raw = serialize(value, using=serializer)
    else:
        raw = serialize(value)

    if deserializer is not None:
        new_value = deserialize(raw, using=deserializer)
    else:
        new_value = deserialize(raw, to=type(value))

    assert new_value == value


@pytest.mark.parametrize(
    ("value", "serializer"),
    [  # pyright: ignore[reportUnknownArgumentType]
        (BrokenSerializable(), None),
        ("anything", broken_serializer),
        (circular_list, None),
    ],
)
def test_serialize_raises_error[T](value: T, serializer: Callable[[T], bytes] | None) -> None:
    with pytest.raises(SerializationError, match="Failed to serialize value:"):
        if serializer is not None:
            _ = serialize(value, using=serializer)
        else:
            _ = serialize(value)


@pytest.mark.parametrize(
    ("value", "deserializer", "target"),
    [
        (b"anything", broken_deserializer, None),
        (b"invalid json", None, dict),
        (b'{"nested": {}}', None, ModelWithRequired),
        (b'{"positive_number": -1}', None, ModelWithConstraints),
        (b'"string"', None, int),
    ],
)
def test_deserialize_raises_error[T](
    value: bytes,
    deserializer: Callable[[bytes], T] | None,
    target: type[T] | None,
) -> None:
    with pytest.raises(DeserializationError, match="Failed to deserialize value:"):
        if deserializer is not None:
            _ = deserialize(value, using=deserializer)
        elif target is not None:
            _ = deserialize(value, to=target)
        else:
            pytest.fail("No deserializer or target type provided")
