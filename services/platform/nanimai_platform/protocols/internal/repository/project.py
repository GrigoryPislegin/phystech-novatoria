from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from nanimai_platform.domain import Project, ProjectID, UserID, VacancyID
from nanimai_platform.domain.project.project import ProjectStatistics
from nanimai_platform.utils.update_value import UpdateValue


class ProjectRepositoryError(Exception): ...


class ProjectValidateError(ProjectRepositoryError): ...


class ProjectNotFoundError(ProjectRepositoryError): ...


class CreateProjectError(ProjectRepositoryError): ...


class ReadProjectError(ProjectRepositoryError): ...


class UpdateProjectError(ProjectRepositoryError): ...


class DeleteProjectError(ProjectRepositoryError): ...


class ProjectRepositoryProtocol(ABC):
    @dataclass
    class CreateProjectRequest:
        user_id: UserID
        title: str
        thumbnail_url: str
        statistics: ProjectStatistics
        description: str | None = None

    @abstractmethod
    async def create_project(self, request: CreateProjectRequest) -> Project:
        """creates project in repository

        Raises:
            CreateProjectError - not expected exception
            ProjectValidateError - validation error
        Returns:
            Project - created project
        """
        ...

    @dataclass
    class ReadProjectRequest:
        id: ProjectID

    @abstractmethod
    async def read_project(self, request: ReadProjectRequest) -> Project:
        """reads project in repository

        Raises:
            ReadProjectError - not expected exception
            ProjectValidateError - validation error
            ProjectNotFoundError - project not found
        Returns:
            Project - read project
        """
        ...

    @dataclass
    class UpdateProjectRequest:
        id: ProjectID
        title: UpdateValue[str] | None = None
        description: UpdateValue[str | None] | None = None
        thumbnail_url: UpdateValue[str] | None = None
        vacancies: UpdateValue[list[VacancyID]] | None = None
        statistics: UpdateValue[ProjectStatistics] | None = None
        updated_at: UpdateValue[datetime] | None = None

    @abstractmethod
    async def update_project(self, request: UpdateProjectRequest) -> Project:
        """updates project in repository

        Raises:
            UpdateProjectError - not expected exception
            ProjectValidateError - validation error
            ProjectNotFoundError - project not found
        Returns:
            Project - updated project
        """
        ...

    @dataclass
    class DeleteProjectRequest:
        id: ProjectID

    @abstractmethod
    async def delete_project(self, request: DeleteProjectRequest) -> Project:
        """deletes project in repository

        Raises:
            DeleteProjectError - not expected exception
            ProjectValidateError - validation error
            ProjectNotFoundError - project not found
        Returns:
            Project - deleted project
        """
        ...

    @dataclass
    class ReadManyProjectsRequest:
        project_ids: list[ProjectID]

    @abstractmethod
    async def read_many_projects(self, request: ReadManyProjectsRequest) -> list[Project | None]:
        """reads many projects in repository

        Raises:
            ReadProjectError - not expected exception
            ProjectValidateError - validation error
            ProjectNotFoundError - project not found
        Returns:
            list[Project | None] - list of projects or None if project does not exist
        """
        ...

    @dataclass
    class ReadManyProjectsByUserRequest:
        user_id: UserID

    @abstractmethod
    async def read_many_projects_by_user(self, request: ReadManyProjectsByUserRequest) -> list[Project]:
        """reads many projects by user in repository

        Raises:
            ReadProjectError - not expected exception
            ProjectValidateError - validation error
        Returns:
            list[Project] - list of projects
        """
        ...

    @dataclass
    class UpdateProjectSettingsRequest:
        id: ProjectID
        logo_url: str | None
        logo_format: str | None
        main_color: str | None
        without_nanimai_attributes: bool

    @abstractmethod
    async def update_project_settings(self, request: UpdateProjectSettingsRequest) -> Project:
        """updates project settings in repository

        Raises:
            UpdateProjectError - not expected exception
            ProjectValidateError - validation error
            ProjectNotFoundError - project not found
        Returns:
            Project - updated project
        """
        ...
