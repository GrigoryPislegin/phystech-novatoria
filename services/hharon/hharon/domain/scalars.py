import builtins
from typing import Self
from uuid import UUID, SafeUUID, uuid4

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema

UUID4_VERSION = 4


class BaseUUID4(UUID):
    def __init__(  # noqa: PLR0913
        self,
        hex: builtins.str | None = None,  # noqa: A002
        bytes: builtins.bytes | None = None,  # noqa: A002
        bytes_le: builtins.bytes | None = None,
        fields: tuple[builtins.int, builtins.int, builtins.int, builtins.int, builtins.int, builtins.int] | None = None,
        int: builtins.int | None = None,  # noqa: A002
        version: builtins.int | None = None,
        *,
        is_safe: SafeUUID = SafeUUID.unknown,
    ):

        if not any([hex, bytes, bytes_le, fields, int]):
            obj = uuid4()
            bytes = obj.bytes  # noqa: A001
            version = obj.version

        super().__init__(hex, bytes, bytes_le, fields, int, version, is_safe=is_safe)

        if self.version != UUID4_VERSION:
            raise ValueError("not UUIDv4")

    @classmethod
    def from_uuid(cls, other: UUID) -> Self:
        return cls(bytes=other.bytes)

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: type, handler: GetCoreSchemaHandler) -> CoreSchema:
        return core_schema.no_info_after_validator_function(cls.from_uuid, core_schema.uuid_schema())


class TaskID(BaseUUID4):
    pass


class HharonUserID(BaseUUID4):
    pass


class ResponseCollectionSettingsID(BaseUUID4):
    pass


class SearchCampaignID(BaseUUID4):
    pass
