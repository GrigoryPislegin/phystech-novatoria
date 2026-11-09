from datetime import UTC, datetime

from fastapi_camelcase import CamelModel


def to_utc_isoformat(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


class DTOBase(CamelModel):
    class Config:
        json_encoders = {datetime: to_utc_isoformat}  # pyright: ignore[reportUnannotatedClassAttribute]
