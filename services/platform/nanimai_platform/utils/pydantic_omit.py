from typing import Any, override

from pydantic import BaseModel
from pydantic_core import PydanticUndefined


class OmitId(BaseModel):
    @classmethod
    @override
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:  # pyright: ignore[reportAny,reportExplicitAny]
        super().__pydantic_init_subclass__(**kwargs)

        for name, field in list(cls.model_fields.items()):
            if name == "id":
                field.default = PydanticUndefined
                del cls.model_fields[name]

        _ = cls.model_rebuild(force=True)


class OmitTime(BaseModel):
    @classmethod
    @override
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:  # pyright: ignore[reportAny,reportExplicitAny]
        super().__pydantic_init_subclass__(**kwargs)

        for name, field in list(cls.model_fields.items()):
            if name == "created_at" or name == "updated_at" or name == "deleted_at":
                field.default = PydanticUndefined
                del cls.model_fields[name]

        _ = cls.model_rebuild(force=True)
