from pydantic import Field

from nanimai_platform.cmd.server.utils.dtobase import DTOBase
from nanimai_platform.domain import UserID, VacancyID


class BalanceResponseDTO(DTOBase):
    balance_id: str
    user_id: UserID
    current: int = Field(ge=0)
    maximum: int = Field(ge=0)
    reserved: int = Field(ge=0)


class PostLimitRequestDTO(DTOBase):
    vacancy_id: VacancyID
    maximum: int = Field(ge=0)


class UpsertLimitRequestDTO(DTOBase):
    maximum: int = Field(ge=0)


class LimitResponseDTO(DTOBase):
    limit_id: str
    balance_id: str
    resource_id: str
    current: int = Field(ge=0)
    maximum: int = Field(ge=0)


class GetManyLimitsResponseDTO(DTOBase):
    limits: list[LimitResponseDTO]


class GetSingleLimitResponseDTO(DTOBase):
    limit: LimitResponseDTO | None
