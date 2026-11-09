from pydantic import BaseModel, Field

from nanimai_platform.domain.scalar.scalars import ProjectID, StopFactorID, UserID, VacancyID
from nanimai_platform.utils import TimeBaseModel


class StopFactor(TimeBaseModel):
    id: StopFactorID = Field(description="stop-factor id")
    user_id: UserID = Field(description="user id")
    project_id: ProjectID = Field(description="project id")
    vacancy_id: VacancyID = Field(description="vacancy id")
    stop_factor: str = Field(description="stop-factor text")
    initial_weight: int = Field(ge=0, le=100, description="initial weight")


class StopFactorPayload(BaseModel):
    stop_factor: str = Field(description="stop-factor text")
    initial_weight: int = Field(ge=0, le=100, description="initial weight")
