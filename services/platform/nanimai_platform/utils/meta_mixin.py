from typing import Any

from pydantic import BaseModel, Field


class MetaMixin(BaseModel):
    meta: dict[str, Any] = Field(default_factory=dict)  # pyright: ignore[reportExplicitAny]
