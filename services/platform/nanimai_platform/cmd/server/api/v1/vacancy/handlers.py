from typing import Annotated, Literal

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nanimai_platform.cmd.server.api.v1.vacancy.dto import (
    AddVacancyPublicationRequestDTO,
    GetAllVacanciesResponseDTO,
    ImportVacancyRequestDTO,
    ImportVacancyResponseDTO,
    PostVacancyRequestDTO,
    PutVacancyRequestDTO,
    VacancyPublicationPreviewDTO,
    VacancyResponseDTO,
)
from nanimai_platform.cmd.server.api.v1.vacancy.statistics_dto import (
    ManyStatisticsResponseDTO,
    StatisticsResponseDTO,
)
from nanimai_platform.cmd.server.dependencies import authorized
from nanimai_platform.domain.criterion.criterion import CriterionPayload
from nanimai_platform.domain.oauth2_profile.oauth2_profile import Oauth2SourceEnum
from nanimai_platform.domain.scalar.scalars import ProjectID, VacancyID
from nanimai_platform.domain.skill.skill import Skill
from nanimai_platform.domain.stop_factor.stop_factor import StopFactorPayload
from nanimai_platform.domain.vacancy.vacancy import SalaryAmountRange, VacancyStageStatus
from nanimai_platform.services.authorization.service import AuthorizationService
from nanimai_platform.services.candidate.service import (
    CandidateServiceError,
    CandidateServiceInvalidDataError,
)
from nanimai_platform.services.criterion import CriterionService
from nanimai_platform.services.publisher.service import (
    PublisherService,
    PublisherServiceError,
    PublisherServiceInvalidDataError,
    PublisherServiceOAuth2Error,
    PublisherServiceWrongVacancyUrlError,
)
from nanimai_platform.services.statistics.service import (
    StatisticsService,
    StatisticsServiceError,
    StatisticsServiceInvalidDataError,
    StatisticsServiceProjectNotFoundError,
    StatisticsServiceStatisticsNotFoundError,
)
from nanimai_platform.services.stop_factor import StopFactorService
from nanimai_platform.services.vacancy.rich_update_hook import (
    VacancyRichUpdateHook,
    VacancyRichUpdateHookCriterionNotFoundError,
    VacancyRichUpdateHookError,
    VacancyRichUpdateHookHHaronError,
    VacancyRichUpdateHookInvalidDataError,
    VacancyRichUpdateHookStopFactorNotFoundError,
    VacancyRichUpdateHookVacancyNotFoundError,
)
from nanimai_platform.services.vacancy.service import (
    VacancyService,
    VacancyServiceError,
    VacancyServiceInvalidDataError,
    VacancyServiceOAuth2Error,
    VacancyServiceProjectNotFoundError,
    VacancyServiceVacancyNotFoundError,
    VacancyServiceWrongVacancyUrlError,
)
from nanimai_platform.services.vacancy_importer.service import (
    VacancyImporterService,
    VacancyImporterServiceError,
    VacancyImporterServiceWrongURLFormatError,
)

router = APIRouter(tags=["vacancy"])

log = structlog.stdlib.get_logger("app.router.vacancy")


@router.get("/")
@inject
async def get_all_vacancies_in_project_handler(
    *,
    project_id: ProjectID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    vacancy_service: FromDishka[VacancyService],
    auth_service: FromDishka[AuthorizationService],
) -> GetAllVacanciesResponseDTO:
    log.debug("Getting all vacancies for project", project_id=project_id)
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        vacancies = await vacancy_service.read_many_by_project(
            VacancyService.ReadManyByProjectRequest(project_id=project_id)
        )

        return GetAllVacanciesResponseDTO(vacancies=[VacancyResponseDTO.from_domain(vacancy) for vacancy in vacancies])
    except VacancyServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except VacancyServiceProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Проект не найден, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось получить кандидатов, попробуйте снова спустя некоторое время",
        ) from e
    except VacancyServiceError as e:
        log.error("Internal server error when getting vacancies", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("Unable to read vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e


@router.get("/statistics")
@inject
async def get_many_statistics_by_project_handler(
    *,
    project_id: Annotated[ProjectID, Query()],
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    statistics_service: FromDishka[StatisticsService],
    auth_service: FromDishka[AuthorizationService],
) -> ManyStatisticsResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        many_statistics = await statistics_service.read_many_by_project(
            StatisticsService.ReadManyStatisticsByProjectRequest(project_id=project_id)
        )
        return ManyStatisticsResponseDTO.from_domain(many_statistics)

    except StatisticsServiceInvalidDataError as e:
        log.error("Invalid data in request", err=e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except StatisticsServiceProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Организация не найдена, попробуйте перезагрузить страницу",
        ) from e
    except StatisticsServiceError as e:
        log.error("Internal server error when getting statistics", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("Unable to read vacancy statistics", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e


@router.get("/{vacancy_id}/statistics")
@inject
async def get_vacancy_statistics_handler(
    *,
    vacancy_id: VacancyID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    statistics_service: FromDishka[StatisticsService],
    auth_service: FromDishka[AuthorizationService],
) -> StatisticsResponseDTO | None:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        statistics = await statistics_service.read_by_vacancy(
            StatisticsService.ReadStatisticsByVacancyRequest(vacancy_id=vacancy_id)
        )
        return StatisticsResponseDTO.from_domain(statistics)
    except StatisticsServiceStatisticsNotFoundError:
        return None
    except StatisticsServiceInvalidDataError as e:
        log.error("Invalid data in request", err=e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except StatisticsServiceError as e:
        log.error("Internal server error when getting vacancy statistics", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e


@router.get("/{vacancy_id}")
@inject
async def get_vacancy_handler(
    *,
    vacancy_id: VacancyID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    vacancy_service: FromDishka[VacancyService],
    auth_service: FromDishka[AuthorizationService],
) -> VacancyResponseDTO:
    log.debug("Getting vacancy details", vacancy_id=vacancy_id)
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        vacancy = await vacancy_service.read(VacancyService.ReadVacancyRequest(id=vacancy_id))
        return VacancyResponseDTO.from_domain(vacancy)

    except VacancyServiceInvalidDataError as e:
        log.error("Invalid data in request", err=e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except VacancyServiceVacancyNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вакансия не найдена, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось получить кандидатов, попробуйте снова спустя некоторое время",
        ) from e
    except VacancyServiceError as e:
        log.error("Internal server error when getting vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("Unable to read vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e


@router.post("/")
@inject
async def post_vacancy_handler(  # noqa: C901
    *,
    request_body: PostVacancyRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    criterion_service: FromDishka[CriterionService],
    stop_factor_service: FromDishka[StopFactorService],
    vacancy_service: FromDishka[VacancyService],
    authorization: FromDishka[AuthorizationService],
    publisher: FromDishka[PublisherService],
) -> VacancyResponseDTO:
    log.debug("Creating new vacancy", project_id=request_body.project_id)
    user = await authorized.get_current_user(credentials, authorization)
    try:
        vacancy = await vacancy_service.create(
            VacancyService.CreateVacancyRequest(
                user_id=user.id,
                project_id=request_body.project_id,
                title=request_body.title,
                description=request_body.description,
                specialization=request_body.specialization,
                status=request_body.status,
                city=request_body.city,
                country=request_body.country,
                hire_amount=request_body.hire_amount,
                salary=SalaryAmountRange(
                    currency=request_body.salary.currency,  # pyright: ignore[reportArgumentType]
                    min=request_body.salary.min,
                    max=request_body.salary.max,
                )
                if request_body.salary is not None
                else None,
                work_type=request_body.work_type,
                work_format=request_body.work_format,
                is_internship=request_body.is_internship,
                is_temphire=request_body.is_temphire,
                schedule=request_body.schedule,
                daily_rate=request_body.daily_rate,
                experience=request_body.experience,
                skills=[Skill(title=skill) for skill in request_body.skills],
                stages=[VacancyStageStatus(stage=stage.kind, shown=stage.shown) for stage in request_body.stages]
                if request_body.stages is not None
                else None,
                threshold=request_body.threshold,
            )
        )
        log.debug("Created vacancy", vacancy_id=vacancy.id)

        if request_body.publish_to is not None and request_body.publish_to.hh:
            log.debug("user requested to publish vacancy to hh", vacancy_id=vacancy.id)
            await publisher.publish_vacancy("hh", user, vacancy)

        if request_body.criteria:
            await criterion_service.create_many(
                CriterionService.CreateManyCriteriaRequest(
                    user_id=user.id,
                    project_id=request_body.project_id,
                    vacancy_id=vacancy.id,
                    criteria=[
                        CriterionPayload(
                            criterion=criterion.criterion,
                            initial_weight=criterion.initial_weight,
                        )
                        for criterion in request_body.criteria
                        if criterion
                    ],
                )
            )

        if request_body.stop_factors:
            await stop_factor_service.create_many(
                StopFactorService.CreateManyStopFactorsRequest(
                    user_id=user.id,
                    project_id=request_body.project_id,
                    vacancy_id=vacancy.id,
                    stop_factors=[
                        StopFactorPayload(
                            stop_factor=stop_factor.stop_factor,
                            initial_weight=stop_factor.initial_weight,
                        )
                        for stop_factor in request_body.stop_factors
                        if stop_factor
                    ],
                )
            )

        return VacancyResponseDTO.from_domain(vacancy)
    except VacancyServiceProjectNotFoundError as e:
        log.error("Project not found when creating vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Проект не найден, попробуйте перезагрузить страницу",
        ) from e
    except VacancyServiceInvalidDataError as e:
        log.error("Invalid data when creating vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except VacancyServiceError as e:
        log.error("Internal server error when creating vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("Unable to create vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e


@router.put("/{vacancy_id}")
@inject
async def put_vacancy_handler(
    *,
    vacancy_id: VacancyID,
    request_body: PutVacancyRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    rich_update_vacancy_hook: FromDishka[VacancyRichUpdateHook],
    auth_service: FromDishka[AuthorizationService],
) -> VacancyResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        update_request = request_body.to_update_value(user_id=user.id, vacancy_id=vacancy_id)
        vacancy = await rich_update_vacancy_hook.rich_update_vacancy(update_request)
        return VacancyResponseDTO.from_domain(vacancy)
    except VacancyRichUpdateHookVacancyNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вакансия не найдена, попробуйте перезагрузить страницу",
        ) from e
    except VacancyRichUpdateHookCriterionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Один или несколько критериев не найдены, попробуйте перезагрузить страницу",
        ) from e
    except VacancyRichUpdateHookStopFactorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Один или несколько стоп-факторов не найдены, попробуйте перезагрузить страницу",
        ) from e
    except VacancyRichUpdateHookInvalidDataError as e:
        log.error("Invalid data when updating vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except VacancyRichUpdateHookError as e:
        log.error("Internal server error when updating vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
    except VacancyRichUpdateHookHHaronError as e:
        log.error("Internal server error when completing response collection and search campaign execution", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("Unable to update vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e


@router.delete("/{vacancy_id}")
@inject
async def delete_vacancy_handler(
    *,
    vacancy_id: VacancyID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    vacancy_service: FromDishka[VacancyService],
    auth_service: FromDishka[AuthorizationService],
) -> VacancyResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        vacancy = await vacancy_service.delete(VacancyService.DeleteVacancyRequest(id=vacancy_id))
        return VacancyResponseDTO.from_domain(vacancy)
    except VacancyServiceVacancyNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вакансия не найдена, попробуйте перезагрузить страницу",
        ) from e
    except VacancyServiceInvalidDataError as e:
        log.error("Invalid data when updating vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось получить кандидатов, попробуйте снова спустя некоторое время",
        ) from e
    except VacancyServiceError as e:
        log.error("Internal server error when deleting vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось удалить вакансию, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("Unable to delete vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e


@router.post("/import")
@inject
async def import_vacancy_handler(
    *,
    source: Literal["hh"],
    request: ImportVacancyRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    vacancy_importer_service: FromDishka[VacancyImporterService],
    auth_service: FromDishka[AuthorizationService],
) -> ImportVacancyResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        vacancy = await vacancy_importer_service.import_vacancy(
            vacancy_importer_service.ImportVacancyRequest(
                url=request.url,
                source=source,
                user_id=user.id,
            )
        )
        return ImportVacancyResponseDTO.from_service(vacancy)
    except VacancyImporterServiceWrongURLFormatError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Неверная ссылка на вакансию",
        ) from e
    except VacancyImporterServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось импортировать вакансию, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e


@router.post("/publication")
@inject
async def add_vacancy_publication_handler(
    *,
    source: Literal["hh"],
    vacancy_id: VacancyID,
    request_body: AddVacancyPublicationRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    vacancy_service: FromDishka[VacancyService],
    auth_service: FromDishka[AuthorizationService],
) -> VacancyResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        vacancy = await vacancy_service.add_vacancy_publication(
            VacancyService.AddVacancyPublicationRequest(
                user_id=user.id,
                vacancy_id=vacancy_id,
                source=Oauth2SourceEnum.HH,
                vacancy_url=request_body.url,
            )
        )
        return VacancyResponseDTO.from_domain(vacancy)
    except VacancyServiceVacancyNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вакансия не найдена, попробуйте перезагрузить страницу",
        ) from e
    except VacancyServiceInvalidDataError as e:
        log.error("Invalid data when updating vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except VacancyServiceWrongVacancyUrlError as e:
        log.error("Error when getting data about vacancy from url", err=e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе была передана ссылка на вакансию, на которую пользователь не имеет прав",
        ) from e
    except VacancyServiceOAuth2Error as e:
        log.error("Error when getting data about vacancy from url", err=e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Пользователь не авторизован через платформу рекрутинга {source}",
        ) from e
    except VacancyServiceError as e:
        log.error("Internal server error when updating vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("Unable to update vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e


@router.post("/publication/preview")
@inject
async def vacancy_publication_preview_handler(
    *,
    source: Literal["hh"],
    request_body: AddVacancyPublicationRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    auth_service: FromDishka[AuthorizationService],
    publisher_service: FromDishka[PublisherService],
) -> VacancyPublicationPreviewDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        response = await publisher_service.preview_vacancy_publication(
            PublisherService.PreviewVacancyPublicationRequest(
                user_id=user.id,
                url=request_body.url,
                source=source,
            )
        )

        return VacancyPublicationPreviewDTO(
            title=response.title,
            count=response.count,
            city=response.city,
            published_until=response.published_until,
        )
    except PublisherServiceInvalidDataError as e:
        log.error("Invalid data", err=e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except PublisherServiceWrongVacancyUrlError as e:
        log.error("Error when getting data about vacancy from url", err=e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе была передана ссылка на вакансию, на которую пользователь не имеет прав",
        ) from e
    except PublisherServiceOAuth2Error as e:
        log.error("Error when getting data about vacancy from url", err=e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Пользователь не авторизован через платформу рекрутинга {source}",
        ) from e
    except PublisherServiceError as e:
        log.error("Internal server error when previewing vacancy publication", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("Unable to preview vacancy publication", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
