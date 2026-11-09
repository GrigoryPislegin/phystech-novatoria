from typing import Annotated

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nanimai_platform.cmd.server.api.v1.project.dto import (
    GetAllProjetsResponseDTO,
    PostProjectRequestDTO,
    ProjectResponseDTO,
    ProjectTemplateSettingsDTO,
    PutProjectRequestDTO,
    PutProjectTemplateSettingsRequestDTO,
)
from nanimai_platform.cmd.server.api.v1.project.preview_resume_dto import (
    PostPreviewResumeRequestDTO,
    PostPreviewResumeResponseDTO,
)
from nanimai_platform.cmd.server.dependencies import authorized
from nanimai_platform.domain import ProjectID
from nanimai_platform.services import ResumePreviewServiceError, ResumePreviewServiceValidateError
from nanimai_platform.services.authorization.service import AuthorizationService
from nanimai_platform.services.project import (
    ProjectService,
    ProjectServiceError,
    ProjectServiceInvalidDataError,
    ProjectServiceProjectNotFoundError,
    ProjectServiceUserNotFound,
)
from nanimai_platform.services.resume_preview import ResumePreviewService
from nanimai_platform.utils import UpdateValue

log = structlog.stdlib.get_logger("app.router.project")

router = APIRouter(tags=["project"])


@router.get("/")
@inject
async def get_all_projects_handler(
    *,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    project_service: FromDishka[ProjectService],
    auth_service: FromDishka[AuthorizationService],
) -> GetAllProjetsResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)

    try:
        projects = await project_service.read_many_by_user(ProjectService.ReadManyByUserRequest(user_id=user.id))
        return GetAllProjetsResponseDTO(projects=[ProjectResponseDTO.from_domain(project) for project in projects])
    except ProjectServiceUserNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден, попробуйте перезагрузить страницу",
        ) from e
    except ProjectServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e


@router.get("/{project_id}")
@inject
async def get_project_handler(
    *,
    project_id: ProjectID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    project_service: FromDishka[ProjectService],
    auth_service: FromDishka[AuthorizationService],
) -> ProjectResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        project = await project_service.read(ProjectService.ReadProjectRequest(id=project_id))
        return ProjectResponseDTO.from_domain(project)
    except ProjectServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except ProjectServiceProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Проект не найден, попробуйте перезагрузить страницу",
        ) from e
    except ProjectServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to read project",
        ) from e


@router.post("/")
@inject
async def post_project_handler(
    *,
    request_body: PostProjectRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    project_service: FromDishka[ProjectService],
    auth_service: FromDishka[AuthorizationService],
) -> ProjectResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        project = await project_service.create(
            ProjectService.CreateProjectRequest(
                user_id=user.id,
                title=request_body.title,
                description=request_body.description,
            )
        )
        return ProjectResponseDTO.from_domain(project)
    except ProjectServiceUserNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден, попробуйте перезагрузить страницу",
        ) from e
    except ProjectServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except ProjectServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create project",
        ) from e


@router.put("/template_settings/{project_id}")
@inject
async def put_project_template_settings_handler(
    *,
    project_id: ProjectID,
    request_body: PutProjectTemplateSettingsRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    project_service: FromDishka[ProjectService],
    auth_service: FromDishka[AuthorizationService],
) -> ProjectTemplateSettingsDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        settings = await project_service.update_project_settings(
            ProjectService.UpdateProjectSettingsRequest(
                id=project_id,
                logo=UpdateValue(value=request_body.logo) if "logo" in request_body.model_fields_set else None,
                logo_format=UpdateValue(value=request_body.logo_format)
                if "logo_format" in request_body.model_fields_set
                else None,
                main_color=UpdateValue(value=request_body.main_color)
                if "main_color" in request_body.model_fields_set
                else None,
                without_nanimai_attributes=UpdateValue(request_body.without_nanimai_attributes)
                if "without_nanimai_attributes" in request_body.model_fields_set
                and request_body.without_nanimai_attributes is not None
                else None,
            )
        )
        return ProjectTemplateSettingsDTO(
            logo=settings.logo_data_uri,
            logo_format=settings.logo_format,
            main_color=settings.main_color,
            without_nanimai_attributes=settings.without_nanimai_attributes,
        )
    except ProjectServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except ProjectServiceProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Проект не найден, попробуйте перезагрузить страницу",
        ) from e
    except ProjectServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить проект, попробуйте снова спустя некоторое время",
        ) from e


@router.get("/template_settings/{project_id}")
@inject
async def get_project_template_settings_handler(
    *,
    project_id: ProjectID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    project_service: FromDishka[ProjectService],
    auth_service: FromDishka[AuthorizationService],
) -> ProjectTemplateSettingsDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        settings = await project_service.get_project_settings(ProjectService.GetProjectSettingsRequest(id=project_id))

        return ProjectTemplateSettingsDTO(
            logo=settings.logo_data_uri,
            logo_format=settings.logo_format,
            main_color=settings.main_color,
            without_nanimai_attributes=settings.without_nanimai_attributes,
        )
    except ProjectServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except ProjectServiceProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Проект не найден, попробуйте перезагрузить страницу",
        ) from e
    except ProjectServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить проект, попробуйте снова спустя некоторое время",
        ) from e


@router.put("/{project_id}")
@inject
async def put_project_handler(
    *,
    project_id: ProjectID,
    request_body: PutProjectRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    project_service: FromDishka[ProjectService],
    auth_service: FromDishka[AuthorizationService],
) -> ProjectResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        fields_set = request_body.model_fields_set
        project = await project_service.update(
            ProjectService.UpdateProjectRequest(
                id=project_id,
                title=(
                    UpdateValue(request_body.title)
                    if "title" in fields_set and request_body.title is not None
                    else None
                ),
                description=UpdateValue(request_body.description) if "description" in fields_set else None,
            )
        )
        return ProjectResponseDTO.from_domain(project)
    except ProjectServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except ProjectServiceProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Проект не найден, попробуйте перезагрузить страницу",
        ) from e
    except ProjectServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить проект, попробуйте снова спустя некоторое время",
        ) from e


@router.delete("/{project_id}")
@inject
async def delete_project_handler(
    *,
    project_id: ProjectID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    project_service: FromDishka[ProjectService],
    auth_service: FromDishka[AuthorizationService],
) -> ProjectResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        project = await project_service.delete(ProjectService.DeleteProjectRequest(id=project_id))
        return ProjectResponseDTO.from_domain(project)
    except ProjectServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except ProjectServiceProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Проект не найден, попробуйте перезагрузить страницу",
        ) from e
    except ProjectServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось удалить проект, попробуйте снова спустя некоторое время",
        ) from e


@router.post("/preview_resume")
@inject
async def post_preview_resume_handler(
    *,
    request: PostPreviewResumeRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    resume_preview_service: FromDishka[ResumePreviewService],
    auth_service: FromDishka[AuthorizationService],
) -> PostPreviewResumeResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        response = await resume_preview_service.preview_resume_generation(
            ResumePreviewService.PreviewResumeGenerationRequest(
                logo_data_uri=request.logo,
                logo_format=request.logo_format,
                main_color=request.main_color,
                without_nanimai_attributes=request.without_nanimai_attributes,
            )
        )
        return PostPreviewResumeResponseDTO(download_link=response.preview_url)
    except ResumePreviewServiceValidateError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные",
        ) from e
    except ResumePreviewServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось сгенерировать превью резюме",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось сгенерировать превью резюме",
        ) from e
