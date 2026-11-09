from collections.abc import Callable
from typing import overload

from pydantic import PydanticSchemaGenerationError, TypeAdapter


class SerializationError(Exception):
    pass


class DeserializationError(Exception):
    pass


def build_default_serializer[T](t: type[T]) -> Callable[[T], bytes]:
    """
    Default serializer using Pydantic's TypeAdapter to serialize the value.
    """
    try:
        adapter = TypeAdapter[T](t)
    except PydanticSchemaGenerationError as e:
        msg = f"Failed to serialize value: failed to generate schema for type {t}"
        raise SerializationError(msg) from e

    def serializer(value: T) -> bytes:
        return adapter.dump_json(value, ensure_ascii=False)

    return serializer


def build_default_deserializer[T](t: type[T]) -> Callable[[bytes], T]:
    """
    Default deserializer using Pydantic's TypeAdapter to deserialize the value.
    """
    try:
        adapter = TypeAdapter[T](t)
    except PydanticSchemaGenerationError as e:
        msg = f"Failed to deserialize value: failed to generate schema for type {t}"
        raise SerializationError(msg) from e

    def deserializer(value: bytes) -> T:
        return adapter.validate_json(value, extra="ignore")

    return deserializer


def serialize[T](value: T, *, using: Callable[[T], bytes] | None = None) -> bytes:
    """
    Serialize value using the provided serializer function or the default serializer.

    Default serializer uses Pydantic's TypeAdapter to serialize the value.
    """
    serializer = using
    if serializer is None:
        serializer = build_default_serializer(type(value))

    try:
        return serializer(value)
    except Exception as e:
        msg = f"Failed to serialize value: {value!r}"
        raise SerializationError(msg) from e


@overload
def deserialize[T](value: bytes, *, using: Callable[[bytes], T]) -> T: ...
@overload
def deserialize[T](value: bytes, *, to: type[T]) -> T: ...


def deserialize[T](value: bytes, *, to: type[T] | None = None, using: Callable[[bytes], T] | None = None) -> T:
    """
    Deserialize value using the provided deserializer function or the default deserializer.

    Default deserializer uses Pydantic's TypeAdapter to deserialize the value.
    """
    deserializer = using
    if deserializer is None:
        if to is None:
            raise DeserializationError("either 'to' or 'using' must be provided")

        deserializer = build_default_deserializer(to)

    try:
        return deserializer(value)
    except Exception as e:
        msg = f"Failed to deserialize value: {value!r}"
        raise DeserializationError(msg) from e
