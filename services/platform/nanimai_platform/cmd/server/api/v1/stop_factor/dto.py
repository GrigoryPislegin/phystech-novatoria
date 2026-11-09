from datetime import datetime

from pydantic import Field

from nanimai_platform.cmd.server.utils.dtobase import DTOBase
from nanimai_platform.domain.scalar import ProjectID, StopFactorID, UserID, VacancyID


class StopFactorResponseDTO(DTOBase):
    id: StopFactorID
    created_at: datetime
    updated_at: datetime
    user_id: UserID
    project_id: ProjectID
    vacancy_id: VacancyID
    stop_factor: str
    initial_weight: int = Field(ge=0, le=100)


class GetManyStopFactorsResponseDTO(DTOBase):
    stop_factors: list[StopFactorResponseDTO]


class PostStopFactorRequestDTO(DTOBase):
    vacancy_id: VacancyID
    stop_factor: str
    initial_weight: int = Field(ge=0, le=100)


class PutStopFactorRequestDTO(DTOBase):
    stop_factor: str | None = None
    initial_weight: int | None = Field(ge=0, le=100, default=None)
