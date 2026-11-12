from datetime import datetime

from pydantic import Field

from nanimai_platform.cmd.server.utils.dtobase import DTOBase
from nanimai_platform.domain.scalar import CriterionID, ProjectID, UserID, VacancyID


class CriterionResponseDTO(DTOBase):
    id: CriterionID
    created_at: datetime
    updated_at: datetime
    user_id: UserID
    project_id: ProjectID
    vacancy_id: VacancyID
    criterion: str
    initial_weight: int = Field(ge=0)
    weight: float = Field(ge=0, le=1, default=0)


class GetManyCriteriaResponseDTO(DTOBase):
    criteria: list[CriterionResponseDTO]


class PostCriterionRequestDTO(DTOBase):
    vacancy_id: VacancyID
    criterion: str
    initial_weight: int = Field(ge=0)


class PutCriterionRequestDTO(DTOBase):
    criterion: str | None = None
    initial_weight: int | None = Field(ge=0, default=None)
