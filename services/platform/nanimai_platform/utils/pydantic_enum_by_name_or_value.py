from __future__ import annotations

from enum import Enum

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema


def ByNameOrValue(enum_class: type[Enum]) -> type:
    """
    Factory that returns a base class making Pydantic serialize/deserialize an enum by member *name* or value.
    JsonSchema specifies only names as enum values.

    Usage:
        class Color(Enum):
            RED = 1
            GREEN = 2

        class MyModel(BaseModel):
            color: Annotated[Color, ByNameOrValue(Color)]

        m = MyModel.model_validate({"color": "red"})
        assert m.color is Color.RED          # enum singleton, not a string
        assert m.model_dump() == {"color": "red"}

        m = MyModel.model_validate({"color": 2})
        assert m.color is Color.GREEN          # enum singleton, not a int
        assert m.model_dump() == {"color": "green"}
    """

    class EnumByNameOrValue:
        @classmethod
        def __get_pydantic_core_schema__(
            cls, source_type: object, handler: GetCoreSchemaHandler
        ) -> core_schema.CoreSchema:
            valid_names = [m.name for m in enum_class]

            def deserialize(value: object) -> Enum:
                if isinstance(value, enum_class):
                    return value

                if isinstance(value, str):
                    try:
                        return enum_class[value.upper()]
                    except KeyError as e:
                        raise ValueError(
                            f"{value!r} is not a valid name for {enum_class.__name__}. Expected one of: {valid_names}"
                        ) from e

                try:
                    return enum_class(value)
                except ValueError:
                    pass

                raise ValueError(
                    f"Expected a string name or {enum_class.__name__} instance, got {type(value).__name__!r}"
                )

            def serialize(value: Enum) -> str:
                return value.name.lower()

            return core_schema.no_info_plain_validator_function(
                deserialize,
                serialization=core_schema.plain_serializer_function_ser_schema(
                    serialize,
                    info_arg=False,
                    return_schema=core_schema.str_schema(),
                ),
            )

        @classmethod
        def __get_pydantic_json_schema__(
            cls,
            schema: core_schema.CoreSchema,
            handler: GetJsonSchemaHandler,
        ) -> JsonSchemaValue:
            return {
                "title": enum_class.__name__,
                "type": "string",
                "enum": [m.name.lower() for m in enum_class],
            }

    EnumByNameOrValue.__name__ = f"{enum_class.__name__}ByNameOrValue"
    EnumByNameOrValue.__qualname__ = f"{enum_class.__qualname__}ByNameOrValue"

    return EnumByNameOrValue
