from datetime import datetime

from pydantic import BaseModel, Field


class TimeBaseModel(BaseModel):
    created_at: datetime = Field(
        description=("timestamp of object creation within the system"),
    )

    updated_at: datetime = Field(
        description=("timestamp of last object update within the system"),
    )

    deleted_at: datetime | None = Field(
        description=("timestamp of object deletion within the system"),
    )
