from typing import Any, override

from pydantic import BaseModel


class Partial(BaseModel):
    @classmethod
    @override
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:  # pyright: ignore[reportAny,reportExplicitAny]
        super().__pydantic_init_subclass__(**kwargs)

        for _, field in list(cls.model_fields.items()):
            if field.is_required():
                field.default = None
                field.annotation = type[field.annotation | type(None)]  # type: ignore

        _ = cls.model_rebuild(force=True)
