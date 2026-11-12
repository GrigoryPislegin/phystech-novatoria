from pydantic import BaseModel, Field

from nanimai_platform.domain.scalar.scalars import CriterionID, ProjectID, UserID, VacancyID
from nanimai_platform.utils import TimeBaseModel


class Criterion(TimeBaseModel):
    id: CriterionID = Field(description="criterion id")
    user_id: UserID = Field(description="user id")
    project_id: ProjectID = Field(description="project id")
    vacancy_id: VacancyID = Field(description="vacancy id")
    criterion: str = Field(description="criterion text")
    initial_weight: int = Field(ge=0, description="initial weight")
    weight: float = Field(ge=0, le=1, description="weight of the criterion", default=0)
    calculated: bool = Field(description="whether this criterion is calculated", default=False)


class CriterionPayload(BaseModel):
    criterion: str = Field(description="criterion text")
    initial_weight: int = Field(ge=0, description="initial weight")
