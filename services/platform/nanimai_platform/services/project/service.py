import asyncio
import io
from datetime import UTC, datetime
from typing import final

import structlog
from PIL import Image
from datauri import DataURI
from pydantic import BaseModel, Field

from nanimai_platform.domain.project import Project
from nanimai_platform.domain.project.project import ProjectStatistics
from nanimai_platform.domain.scalar.scalars import ProjectID, UserID, VacancyID
from nanimai_platform.protocols.internal.repository.project import (
    CreateProjectError,
    DeleteProjectError,
    ProjectNotFoundError,
    ProjectRepositoryProtocol,
    ProjectValidateError,
    ReadProjectError,
)
from nanimai_platform.protocols.internal.repository.user_profile import UserNotFoundError, UserRepositoryError
from nanimai_platform.services.cache import Cache
from nanimai_platform.services.cache.keyspace import Key, Keyspace
from nanimai_platform.services.file_storage.service import FileStorageService
from nanimai_platform.services.thumbnail.service import ThumbnailService, ThumbnailServiceError
from nanimai_platform.services.user_profile.service import UserService
from nanimai_platform.utils import UpdateValue
from nanimai_platform.utils.asyncio_background import launch_background
from nanimai_platform.utils.logging_span import span

log = structlog.stdlib.get_logger("app.service.ProjectService")


class ProjectServiceError(Exception): ...


class ProjectServiceInvalidDataError(Exception): ...


class ProjectServiceProjectNotFoundError(Exception): ...


class ProjectServiceUserNotFound(Exception): ...


@final
class ProjectService:
    def __init__(
        self,
        cache: Cache,
        project_repo: ProjectRepositoryProtocol,
        user_service: UserService,
        thumbnail_service: ThumbnailService,
        file_storage: FileStorageService,
    ):
        self._cache = cache
        self._ks = Keyspace("project_service")
        self._project_repo = project_repo
        self._user = user_service
        self._thumbnail_service = thumbnail_service
        self._file_storage = file_storage

    class CreateProjectRequest(BaseModel):
        user_id: UserID
        title: str
        description: str | None = None

    @span(op="project_service", name="create_project")
    async def create(self, request: CreateProjectRequest) -> Project:
        try:
            # assert user exists
            _ = await self._user.read(self._user.ReadUserProfileRequest(id=request.user_id))

            thumbnail_url = await self._thumbnail_service.create_project_thumbnail(request.title)

            project = await self._project_repo.create_project(
                ProjectRepositoryProtocol.CreateProjectRequest(
                    user_id=request.user_id,
                    title=request.title,
                    description=request.description,
                    thumbnail_url=thumbnail_url,
                    statistics=ProjectStatistics(
                        total_candidates=0,
                        total_vacancies=0,
                        active_vacancies=0,
                    ),
                )
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._project_key(project.id), project)
                await self._cache.sadd(self._user_set_key(request.user_id), {"id": str(project.id)})

            update_cache()

            return project
        except ThumbnailServiceError as e:
            log.error("failed to create project due to thumbnail service error", err=e)
            raise ProjectServiceError("failed to create project") from e
        except UserNotFoundError as e:
            log.error("failed to read user", err=e)
            raise ProjectServiceUserNotFound("user not found") from e
        except ProjectValidateError as e:
            log.error("failed to create project due to validation error", err=e)
            raise ProjectServiceInvalidDataError from e
        except CreateProjectError as e:
            log.error("failed to create project", err=e)
            raise ProjectServiceError from e

    class ReadProjectRequest(BaseModel):
        id: ProjectID

    @span(op="project_service", name="read_project")
    async def read(self, request: ReadProjectRequest) -> Project:
        try:
            # try to read from cache
            if (project := await self._cache.get(self._project_key(request.id), t=Project)) is not None:
                return project

            # read from db
            project = await self._project_repo.read_project(ProjectRepositoryProtocol.ReadProjectRequest(id=request.id))

            @launch_background
            async def update_cache():
                await self._cache.set(self._project_key(project.id), project)
                await self._cache.sadd(self._user_set_key(project.user_id), {"id": str(project.id)})

            update_cache()

            return project
        except ProjectValidateError as e:
            log.error("failed to read project due to validation error", err=e)
            raise ProjectServiceInvalidDataError from e
        except ProjectNotFoundError as e:
            log.error("failed to find project", err=e)
            raise ProjectServiceProjectNotFoundError from e
        except ReadProjectError as e:
            log.error("failed to read project", err=e)
            raise ProjectServiceError from e

    class ReadManyProjectsRequest(BaseModel):
        project_ids: list[ProjectID]

    @span(op="project_service", name="read_many_projects")
    async def read_many(self, request: ReadManyProjectsRequest) -> list[Project | None]:  # noqa: C901
        try:
            if len(request.project_ids) == 0:
                return []

            projects = {}

            # try to load as much as possible from cache
            cache_projects = await self._cache.mget([self._project_key(id) for id in request.project_ids], t=Project)

            for project in cache_projects:
                if project is not None:
                    projects[project.id] = project  # store results

            # retrieve from db the rest
            retrieve_from_db = list(set(request.project_ids) - set(projects.keys()))

            db_projects = await self._project_repo.read_many_projects(
                ProjectRepositoryProtocol.ReadManyProjectsRequest(project_ids=retrieve_from_db)
            )
            for project in db_projects:
                if project is not None:
                    projects[project.id] = project

            @launch_background
            async def update_cache():
                # save projects to cache and add to user set
                await self._cache.mset({self._project_key(id): project for id, project in projects.items()})

                grouped_by_user = {}
                for project in projects.values():
                    if project.user_id not in grouped_by_user:
                        grouped_by_user[project.user_id] = []
                    grouped_by_user[project.user_id].append({"id": str(project.id)})

                await asyncio.gather(*[
                    self._cache.sadd(self._user_set_key(user_id), *project_ids)
                    for user_id, project_ids in grouped_by_user.items()
                ])

            update_cache()

            # return projects in the same order as requested
            return [projects.get(project_id, None) for project_id in request.project_ids]
        except ProjectValidateError as e:
            log.error("failed to read many projects due to validation error", err=e)
            raise ProjectServiceInvalidDataError from e
        except ReadProjectError as e:
            log.error("failed to read many projects", err=e)
            raise ProjectServiceError from e

    class UpdateProjectRequest(BaseModel):
        id: ProjectID
        title: UpdateValue[str] | None = None
        description: UpdateValue[str | None] | None = None
        thumbnail_url: UpdateValue[str] | None = None
        vacancies: UpdateValue[list[VacancyID]] | None = None
        statistics: UpdateValue[ProjectStatistics] | None = None

    @span(op="project_service", name="update_project")
    async def update(self, request: UpdateProjectRequest) -> Project:
        try:
            project = await self._project_repo.update_project(
                ProjectRepositoryProtocol.UpdateProjectRequest(
                    id=request.id,
                    title=request.title,
                    description=request.description,
                    thumbnail_url=request.thumbnail_url,
                    vacancies=request.vacancies,
                    statistics=request.statistics,
                    updated_at=UpdateValue(datetime.now(UTC)),
                )
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._project_key(project.id), project)
                await self._cache.sadd(self._user_set_key(project.user_id), {"id": str(project.id)})

            update_cache()

            return project
        except ProjectValidateError as e:
            log.error("failed to update project due to validation error", err=e)
            raise ProjectServiceInvalidDataError from e
        except ProjectNotFoundError as e:
            log.error("failed to find project", err=e)
            raise ProjectServiceProjectNotFoundError from e
        except CreateProjectError as e:
            log.error("failed to update project", err=e)
            raise ProjectServiceError from e

    class DeleteProjectRequest(BaseModel):
        id: ProjectID

    @span(op="project_service", name="delete_project")
    async def delete(self, request: DeleteProjectRequest) -> Project:
        try:
            project = await self._project_repo.delete_project(
                ProjectRepositoryProtocol.DeleteProjectRequest(id=request.id)
            )
            await self._cache.invalidate(self._project_key(project.id))
            await self._cache.srem(self._user_set_key(project.user_id), {"id": str(project.id)})

            return project
        except ProjectValidateError as e:
            log.error("failed to delete project due to validation error", err=e)
            raise ProjectServiceInvalidDataError from e
        except ProjectNotFoundError as e:
            log.error("failed to find project", err=e)
            raise ProjectServiceProjectNotFoundError from e
        except DeleteProjectError as e:
            log.error("failed to delete project", err=e)
            raise ProjectServiceError from e

    class ReadManyByUserRequest(BaseModel):
        user_id: UserID

    @span(op="project_service", name="read_many_projects_by_user")
    async def read_many_by_user(self, request: ReadManyByUserRequest) -> list[Project]:  # noqa: C901
        try:
            projects: dict[ProjectID, Project] = {}

            # assert user exists
            _ = await self._user.read(self._user.ReadUserProfileRequest(id=request.user_id))

            # fetch user set from cache
            projects_set: list[str] = [
                d["id"] for d in (await self._cache.smembers(self._user_set_key(request.user_id)))
            ]

            if not projects_set:  # cache miss
                # read from db
                db_only_projects = await self._project_repo.read_many_projects_by_user(
                    ProjectRepositoryProtocol.ReadManyProjectsByUserRequest(user_id=request.user_id)
                )

                @launch_background
                async def update_cache_from_db():
                    # save projects to cache
                    await self._cache.invalidate(self._user_set_key(request.user_id))

                    if db_only_projects:
                        await self._cache.mset({self._project_key(project.id): project for project in db_only_projects})
                        await self._cache.sadd(
                            self._user_set_key(request.user_id), *[{"id": str(p.id)} for p in db_only_projects]
                        )

                update_cache_from_db()

                return db_only_projects

            # cache hit
            cache_projects = await self._cache.mget(
                [self._project_key(ProjectID(id)) for id in projects_set], t=Project
            )

            # read from cache
            for project in cache_projects:
                if project is not None:
                    projects[project.id] = project

            # read rest from db
            db_projects = await self._project_repo.read_many_projects(
                ProjectRepositoryProtocol.ReadManyProjectsRequest(
                    project_ids=list({ProjectID(id) for id in projects_set} - set(projects.keys()))
                )
            )
            for project in db_projects:
                if project is not None:
                    projects[project.id] = project

            @launch_background
            async def update_cache():
                # save projects to cache

                await self._cache.invalidate(self._user_set_key(request.user_id))

                if projects:
                    await self._cache.mset({self._project_key(project.id): project for project in projects.values()})
                    await self._cache.sadd(
                        self._user_set_key(request.user_id), *[{"id": str(p.id)} for p in projects.values()]
                    )

            update_cache()

            return list(projects.values())
        except ProjectValidateError as e:
            log.error("failed to read many projects by user due to validation error", err=e)
            raise ProjectServiceInvalidDataError from e
        except ReadProjectError as e:
            log.error("failed to read many projects by user", err=e)
            raise ProjectServiceError from e
        except UserRepositoryError as e:
            log.error("failed to read user", err=e)
            raise ProjectServiceUserNotFound("user not found") from e

    class GetProjectSettingsRequest(BaseModel):
        id: ProjectID

    class GetProjectSettingsResponse(BaseModel):
        logo_data_uri: str | None = Field(description="Data URI")
        logo_format: str | None = Field(description="logo format")
        main_color: str | None = Field(description="main color in hex without prefix")
        without_nanimai_attributes: bool = Field(description="True if don't use nanimai attributes")

    async def get_project_settings(
        self, request: GetProjectSettingsRequest
    ) -> "ProjectService.GetProjectSettingsResponse":
        try:
            project = await self.read(self.ReadProjectRequest(id=request.id))

            data_uri = None
            if project.template_settings.logo_url:
                try:
                    logo_bytes = await self._file_storage.download_user_file(
                        project.user_id, project.template_settings.logo_url
                    )

                    data_uri = DataURI.make("image/png", charset=None, base64=True, data=logo_bytes)
                except Exception as e:
                    log.error("failed to retrieve logo data uri", err=e)
                    data_uri = None

            @launch_background
            async def update_cache():
                await self._cache.set(self._project_key(project.id), project)
                await self._cache.sadd(self._user_set_key(project.user_id), {"id": str(project.id)})

            update_cache()

            return self.GetProjectSettingsResponse(
                logo_data_uri=data_uri,
                logo_format=project.template_settings.logo_format,
                main_color=project.template_settings.main_color,
                without_nanimai_attributes=project.template_settings.without_nanimai_attributes,
            )
        except Exception as e:
            log.error("failed to update candidate count", err=e)
            raise ProjectServiceError("failed to update candidate count") from e

    class UpdateProjectSettingsRequest(BaseModel):
        id: ProjectID
        logo: UpdateValue[str | None] | None = Field(default=None)
        logo_format: UpdateValue[str | None] | None = Field(default=None)
        main_color: UpdateValue[str | None] | None = Field(default=None)
        without_nanimai_attributes: UpdateValue[bool] | None = Field(default=None)

    class UpdateProjectSettingsResponse(BaseModel):
        project: Project
        logo_data_uri: str | None

    @span(op="project_service", name="update_project")
    async def update_project_settings(  # noqa: C901
        self, request: UpdateProjectSettingsRequest
    ) -> "ProjectService.GetProjectSettingsResponse":  # noqa: C901
        try:
            if (project_read := await self._cache.get(self._project_key(request.id), t=Project)) is None:
                project_read = await self._project_repo.read_project(
                    ProjectRepositoryProtocol.ReadProjectRequest(id=request.id)
                )

            template_settings = project_read.template_settings

            if isinstance(request.main_color, UpdateValue):
                template_settings.main_color = request.main_color.value

            if isinstance(request.logo_format, UpdateValue):
                template_settings.logo_format = request.logo_format.value

            if isinstance(request.without_nanimai_attributes, UpdateValue):
                template_settings.without_nanimai_attributes = request.without_nanimai_attributes.value

            final_data_uri = None
            if isinstance(request.logo, UpdateValue):
                if request.logo.value is None:
                    template_settings.logo_url = None
                else:
                    try:
                        buffer = io.BytesIO()
                        # convert to png
                        (
                            Image.open(io.BytesIO(DataURI(request.logo.value).data))
                            .convert("RGBA")
                            .save(
                                buffer,
                                format="png",
                                quality=70,
                            )
                        )
                        content = buffer.getvalue()

                        final_data_uri = DataURI.make("image/png", charset=None, base64=True, data=content)

                        filepath = f"/templates/{project_read.id}/logo.png"
                        await self._file_storage.upload_user_file(
                            project_read.user_id,
                            filepath,
                            content,
                        )
                        template_settings.logo_url = filepath
                    except ValueError as e:
                        log.error("failed to convert image", err=e)
                        raise ProjectServiceInvalidDataError("invalid logo data") from e
                    except Exception as e:
                        raise ProjectServiceError() from e

            project = await self._project_repo.update_project_settings(
                ProjectRepositoryProtocol.UpdateProjectSettingsRequest(
                    id=request.id,
                    logo_url=template_settings.logo_url,
                    logo_format=template_settings.logo_format,
                    main_color=template_settings.main_color,
                    without_nanimai_attributes=template_settings.without_nanimai_attributes,
                )
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._project_key(project.id), project)
                await self._cache.sadd(self._user_set_key(project.user_id), {"id": str(project.id)})

            update_cache()

            return self.GetProjectSettingsResponse(
                logo_data_uri=final_data_uri,
                logo_format=project.template_settings.logo_format,
                main_color=project.template_settings.main_color,
                without_nanimai_attributes=project.template_settings.without_nanimai_attributes,
            )
        except ProjectServiceError as e:
            raise e
        except ProjectValidateError as e:
            log.error("failed to update project due to validation error", err=e)
            raise ProjectServiceInvalidDataError from e
        except ProjectNotFoundError as e:
            log.error("failed to find project", err=e)
            raise ProjectServiceProjectNotFoundError from e
        except CreateProjectError as e:
            log.error("failed to update project", err=e)
            raise ProjectServiceError from e

    # ===

    def _project_key(self, project_id: ProjectID) -> Key:
        return self._ks.key("id", str(project_id))

    def _user_set_key(self, user_id: UserID) -> Key:
        return self._ks.key("user_set", str(user_id))
