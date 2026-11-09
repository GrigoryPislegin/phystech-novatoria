from typing import Annotated

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nanimai_platform.cmd.server.api.v1.candidate.dto import (
    CandidateResponseDTO,
    CandidateStatisticsResponseStatisticsDTO,
    GetCandidateStatisticsResponseDTO,
    GetResumeDownloadLinkResponseDTO,
    PostCandidateRequestDTO,
    PutCandidateCriterionRequestDTO,
    PutCandidateManyCriteriaRequestDTO,
    PutCandidateManyStopFactorsRequestDTO,
    PutCandidateRequestDTO,
    PutCandidateStopFactorRequestDTO,
    StatisticsContainerDTO,
)
from nanimai_platform.cmd.server.dependencies import authorized
from nanimai_platform.domain.candidate.candidate import ExpectedSalary
from nanimai_platform.domain.scalar.scalars import CandidateID, CriterionID, StopFactorID, VacancyID
from nanimai_platform.domain.skill.skill import Skill
from nanimai_platform.services import StatisticsService
from nanimai_platform.services.authorization.service import AuthorizationService
from nanimai_platform.services.candidate.service import (
    CandidateService,
    CandidateServiceCandidateNotFoundError,
    CandidateServiceError,
    CandidateServiceInvalidDataError,
    CandidateServiceVacancyNotFoundError,
)
from nanimai_platform.services.resume_download.service import ResumeDownloadService
from nanimai_platform.services.vacancy.service import VacancyService, VacancyServiceError
from nanimai_platform.utils.update_value import UpdateValue

router = APIRouter(tags=["candidate"])

log = structlog.stdlib.get_logger("app.router.candidate")


@router.get("/statistics")
@inject
async def get_statistics_handler(
    *,
    vacancy_id: VacancyID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    statistics_service: FromDishka[StatisticsService],
    auth_service: FromDishka[AuthorizationService],
) -> GetCandidateStatisticsResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        full_stats = await statistics_service.read_by_vacancy(
            statistics_service.ReadStatisticsByVacancyRequest(vacancy_id=vacancy_id)
        )
        vacancy_stats = full_stats.vacancy_statistics
        return GetCandidateStatisticsResponseDTO(
            statistics=CandidateStatisticsResponseStatisticsDTO(
                all_candidates=StatisticsContainerDTO(
                    total=vacancy_stats.total_candidates,
                    today_increase=vacancy_stats.total_today_increase,
                ),
                platform_candidates=StatisticsContainerDTO(
                    total=vacancy_stats.platform_candidates,
                    today_increase=vacancy_stats.platform_today_increase,
                ),
                delegated_candidates=StatisticsContainerDTO(
                    total=vacancy_stats.hh_candidates,
                    today_increase=vacancy_stats.hh_today_increase,
                ),
                dirty_candidates=StatisticsContainerDTO(
                    total=vacancy_stats.total_dirty_candidates, today_increase=vacancy_stats.dirty_today_increase
                ),
            )
        )
    except CandidateServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось получить статистику кандидатов, попробуйте снова спустя некоторое время",
        ) from e


@router.get("/{candidate_id}")
@inject
async def get_candidate_handler(
    *,
    candidate_id: CandidateID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    candidate_service: FromDishka[CandidateService],
    auth_service: FromDishka[AuthorizationService],
) -> CandidateResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        candidate = await candidate_service.read(
            CandidateService.ReadCandidateRequest(id=candidate_id),
        )
        return CandidateResponseDTO.from_domain(candidate)
    except CandidateServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceCandidateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Кандидат не найден, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось прочитать кандидата, попробуйте снова спустя некоторое время",
        ) from e


@router.post("/")
@inject
async def post_candidate_handler(
    *,
    request_body: PostCandidateRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    candidate_service: FromDishka[CandidateService],
    auth_service: FromDishka[AuthorizationService],
    vacancy_service: FromDishka[VacancyService],
) -> CandidateResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        vacancy = await vacancy_service.read(VacancyService.ReadVacancyRequest(id=request_body.vacancy_id))

        candidate = await candidate_service.create(
            CandidateService.CreateCandidateRequest(
                user_id=user.id,
                project_id=vacancy.project_id,
                vacancy_id=vacancy.id,
                resume=request_body.resume,
                name=request_body.name,
                phone_number=request_body.phone_number,
                email=request_body.email,
                website=request_body.website,
                city=request_body.city,
                country=request_body.country,
                experience=request_body.experience,
                expected_salary=ExpectedSalary(
                    currency=request_body.expected_salary.currency,  # pyright: ignore[reportArgumentType]
                    value=request_body.expected_salary.value,
                )
                if request_body.expected_salary is not None
                else None,
                notes=request_body.notes,
                skills=[Skill(title=title) for title in request_body.skills],
                # criteria=request_body.criteria,  # Пока запрещаем создавать
                # stop_factors=request_body.stop_factors,  # Пока запрещаем создавать
            )
        )

        return CandidateResponseDTO.from_domain(candidate)
    except VacancyServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вакансия не найдена, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceVacancyNotFoundError as e:
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
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось создать кандидата, попробуйте снова спустя некоторое время",
        ) from e


@router.put("/{candidate_id}/criteria")
@inject
async def put_candidate_many_criteria_handler(
    *,
    candidate_id: CandidateID,
    request_body: PutCandidateManyCriteriaRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    candidate_service: FromDishka[CandidateService],
    auth_service: FromDishka[AuthorizationService],
) -> CandidateResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        candidate = await candidate_service.set_candidate_criteria(
            CandidateService.SetCandidateCriteriaRequest(
                id=candidate_id,
                updates=[
                    CandidateService.SetCandidateCriterionRequest(
                        criterion_id=update.criterion_id,
                        score=None,
                        status=UpdateValue(update.status) if "status" in update.model_fields_set else None,
                        description=UpdateValue(update.description)
                        if "description" in update.model_fields_set
                        else None,
                    )
                    for update in request_body.criteria
                ],
            )
        )
        if candidate:
            return CandidateResponseDTO.from_domain(candidate)
        else:
            raise CandidateServiceInvalidDataError("no updates provided")
    except CandidateServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceCandidateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Кандидат не найден, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить анализ по критерию у кандидата, попробуйте снова спустя некоторое время",
        ) from e


@router.put("/{candidate_id}/stop_factors")
@inject
async def put_candidate_many_stop_factors_handler(
    *,
    candidate_id: CandidateID,
    request_body: PutCandidateManyStopFactorsRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    candidate_service: FromDishka[CandidateService],
    auth_service: FromDishka[AuthorizationService],
) -> CandidateResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        candidate = await candidate_service.set_candidate_stop_factors(
            CandidateService.SetCandidateStopFactorsRequest(
                id=candidate_id,
                updates=[
                    CandidateService.SetCandidateStopFactorRequest(
                        stop_factor_id=update.stop_factor_id,
                        status=UpdateValue(update.status) if "status" in update.model_fields_set else None,
                        description=UpdateValue(update.description)
                        if "description" in update.model_fields_set
                        else None,
                    )
                    for update in request_body.stop_factors
                ],
            )
        )
        if candidate:
            return CandidateResponseDTO.from_domain(candidate)
        else:
            raise CandidateServiceInvalidDataError("no updates provided")
    except CandidateServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceCandidateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Кандидат не найден, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить анализ по критерию у кандидата, попробуйте снова спустя некоторое время",
        ) from e


@router.put("/{candidate_id}/criteria/{criteria_id}")
@inject
async def put_candidate_criterion_handler(
    *,
    candidate_id: CandidateID,
    criterion_id: CriterionID,
    request_body: PutCandidateCriterionRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    candidate_service: FromDishka[CandidateService],
    auth_service: FromDishka[AuthorizationService],
) -> CandidateResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)

    try:
        fields_set = request_body.model_fields_set
        candidate = await candidate_service.update_candidate_criterion(
            CandidateService.UpdateCandidateCriterionRequest(
                id=candidate_id,
                criterion_id=criterion_id,
                status=UpdateValue(request_body.status) if "status" in fields_set else None,
                description=UpdateValue(request_body.description) if "description" in fields_set else None,
                score=None,
            )
        )

        return CandidateResponseDTO.from_domain(candidate)
    except CandidateServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceCandidateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Кандидат не найден, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить анализ по критерию у кандидата, попробуйте снова спустя некоторое время",
        ) from e


@router.put("/{candidate_id}/stop_factors/{stop_factor_id}")
@inject
async def put_candidate_stop_factor_handler(
    *,
    candidate_id: CandidateID,
    stop_factor_id: StopFactorID,
    request_body: PutCandidateStopFactorRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    candidate_service: FromDishka[CandidateService],
    auth_service: FromDishka[AuthorizationService],
) -> CandidateResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)

    try:
        fields_set = request_body.model_fields_set
        candidate = await candidate_service.update_candidate_stop_factor(
            CandidateService.UpdateCandidateStopFactorRequest(
                id=candidate_id,
                stop_factor_id=stop_factor_id,
                status=UpdateValue(request_body.status) if "status" in fields_set else None,
                description=UpdateValue(request_body.description) if "description" in fields_set else None,
            )
        )

        return CandidateResponseDTO.from_domain(candidate)
    except CandidateServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceCandidateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Кандидат не найден, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить анализ по критерию у кандидата, попробуйте снова спустя некоторое время",
        ) from e


@router.put("/{candidate_id}")
@inject
async def put_candidate_handler(
    *,
    candidate_id: CandidateID,
    request_body: PutCandidateRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    candidate_service: FromDishka[CandidateService],
    auth_service: FromDishka[AuthorizationService],
) -> CandidateResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)

    try:
        _ = user
        fields_set = request_body.model_fields_set
        candidate = await candidate_service.update(
            CandidateService.UpdateCandidateRequest(
                id=candidate_id,
                resume=(
                    UpdateValue(request_body.resume)
                    if "resume" in fields_set and request_body.resume is not None
                    else None
                ),
                name=(
                    UpdateValue(request_body.name) if "name" in fields_set and request_body.name is not None else None
                ),
                phone_number=(UpdateValue(request_body.phone_number) if "phone_number" in fields_set else None),
                email=UpdateValue(request_body.email) if "email" in fields_set else None,
                website=UpdateValue(request_body.website) if "website" in fields_set else None,
                city=UpdateValue(request_body.city) if "city" in fields_set else None,
                country=UpdateValue(request_body.country) if "country" in fields_set else None,
                thumbnail_url=(
                    UpdateValue(request_body.thumbnail_url)
                    if "thumbnail_url" in fields_set and request_body.thumbnail_url is not None
                    else None
                ),
                experience=(
                    UpdateValue(request_body.experience)
                    if "experience" in fields_set and request_body.experience is not None
                    else None
                ),
                expected_salary=(
                    UpdateValue(
                        ExpectedSalary(
                            currency=request_body.expected_salary.currency,  # pyright: ignore[reportArgumentType]
                            value=request_body.expected_salary.value,
                        )
                        if request_body.expected_salary is not None
                        else None
                    )
                    if "expected_salary" in fields_set
                    else None
                ),
                notes=(
                    UpdateValue(request_body.notes)
                    if "notes" in fields_set and request_body.notes is not None
                    else None
                ),
                dirty=(
                    UpdateValue(request_body.dirty)
                    if "dirty" in fields_set and request_body.dirty is not None
                    else None
                ),
                source=(
                    UpdateValue(request_body.source)
                    if "source" in fields_set and request_body.source is not None
                    else None
                ),
                skills=(
                    UpdateValue([Skill(title=title) for title in request_body.skills])
                    if "skills" in fields_set and request_body.skills is not None
                    else None
                ),
                status=(
                    UpdateValue(request_body.status)
                    if "status" in fields_set and request_body.status is not None
                    else None
                ),
            )
        )

        return CandidateResponseDTO.from_domain(candidate)

    except CandidateServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceCandidateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Кандидат не найден, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить кандидата, попробуйте снова спустя некоторое время",
        ) from e


@router.delete("/{candidate_id}")
@inject
async def delete_candidate_handler(
    *,
    candidate_id: CandidateID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    candidate_service: FromDishka[CandidateService],
    auth_service: FromDishka[AuthorizationService],
) -> CandidateResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        candidate = await candidate_service.delete(
            CandidateService.DeleteCandidateRequest(id=candidate_id),
        )

        return CandidateResponseDTO.from_domain(candidate)

    except CandidateServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceCandidateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Кандидат не найден, попробуйте перезагрузить страницу",
        ) from e
    except CandidateServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось удалить кандидата, попробуйте снова спустя некоторое время",
        ) from e


@router.post("/{candidate_id}/download_resume")
@inject
async def post_resume_download_link_handler(
    *,
    candidate_id: CandidateID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    auth_service: FromDishka[AuthorizationService],
    resume_download_service: FromDishka[ResumeDownloadService],
) -> GetResumeDownloadLinkResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        response = await resume_download_service.get_resume_download_link(
            ResumeDownloadService.GetResumeDownloadLinkRequest(
                candidate_id=candidate_id,
            )
        )

        return GetResumeDownloadLinkResponseDTO(download_link=response.download_link)

    except Exception as e:
        log.error("failed to get resume download link", err=e, candidate_id=candidate_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to get resume download link",
        ) from e
