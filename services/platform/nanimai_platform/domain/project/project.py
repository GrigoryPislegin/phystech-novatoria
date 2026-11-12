from pydantic import BaseModel, Field

from nanimai_platform.domain.scalar import ProjectID
from nanimai_platform.domain.scalar.scalars import UserID
from nanimai_platform.utils import TimeBaseModel


class ProjectTemplateSettings(BaseModel):
    logo_url: str | None = Field(description="URL to image logo")
    logo_format: str | None = Field(description="logo format")
    main_color: str | None = Field(description="main color in hex without prefix")
    without_nanimai_attributes: bool = Field(description="True if don't use nanimai attributes")


class ProjectStatistics(BaseModel):
    total_candidates: int = Field(description="number of candidates")

    total_vacancies: int = Field(description="number of vacancies")
    active_vacancies: int = Field(description="number of active vacancies")


class Project(TimeBaseModel):
    id: ProjectID = Field(description="project id")
    user_id: UserID = Field(description="project owner")
    title: str = Field(description="project title")
    description: str | None = Field(description="project description")
    thumbnail_url: str = Field(description="project thumbnail url")
    statistics: ProjectStatistics = Field(description="project statistics")
    template_settings: ProjectTemplateSettings = Field(description="project template settings for logo")
