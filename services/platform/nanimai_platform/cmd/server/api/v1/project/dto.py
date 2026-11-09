from datetime import datetime

from pydantic import Field

from nanimai_platform.cmd.server.utils.dtobase import DTOBase
from nanimai_platform.domain.project.project import Project
from nanimai_platform.domain.scalar import ProjectID
from nanimai_platform.domain.scalar.scalars import UserID


class StatisticsDTO(DTOBase):
    candidates: int
    active_vacancies: int
    archived_vacancies: int


class ProjectResponseStatisticsDTO(StatisticsDTO): ...


class ProjectTemplateSettingsDTO(DTOBase):
    logo: str | None
    logo_format: str | None
    main_color: str | None
    without_nanimai_attributes: bool


class ProjectResponseDTO(DTOBase):
    id: ProjectID
    user_id: UserID
    created_at: datetime
    updated_at: datetime
    title: str
    description: str | None
    thumbnail_url: str

    statistics: ProjectResponseStatisticsDTO

    @staticmethod
    def from_domain(project: Project):
        return ProjectResponseDTO(
            id=project.id,
            user_id=project.user_id,
            created_at=project.created_at,
            updated_at=project.updated_at,
            title=project.title,
            description=project.description,
            thumbnail_url=project.thumbnail_url,
            statistics=ProjectResponseStatisticsDTO(
                candidates=project.statistics.total_candidates,
                active_vacancies=project.statistics.active_vacancies,
                archived_vacancies=project.statistics.total_vacancies - project.statistics.active_vacancies,
            ),
        )


class GetAllProjetsResponseDTO(DTOBase):
    projects: list[ProjectResponseDTO]


class PostProjectRequestDTO(DTOBase):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(max_length=1000, default=None)


class PutProjectRequestDTO(DTOBase):
    title: str | None = Field(min_length=1, max_length=200, default=None)
    description: str | None = Field(max_length=1000, default=None)


class PutProjectTemplateSettingsRequestDTO(DTOBase):
    logo: str | None = None
    logo_format: str | None = None
    main_color: str | None = None
    without_nanimai_attributes: bool | None = None


class ProjectTemplateSettingsResponseDTO(DTOBase):
    logo: str | None = Field(description="data uri")
    logo_format: str | None
    main_color: str | None
    without_nanimai_attributes: bool | None = None
