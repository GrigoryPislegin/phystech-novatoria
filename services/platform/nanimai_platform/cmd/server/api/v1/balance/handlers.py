import asyncio
from typing import Annotated

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nanimai_platform.cmd.server.api.v1.balance.dto import (
    BalanceResponseDTO,
    GetManyLimitsResponseDTO,
    GetSingleLimitResponseDTO,
    LimitResponseDTO,
    PostLimitRequestDTO,
    UpsertLimitRequestDTO,
)
from nanimai_platform.cmd.server.dependencies import authorized
from nanimai_platform.domain import VacancyID
from nanimai_platform.domain.candidate.candidate import CandidateAnalysisStatusEnum
from nanimai_platform.services.authorization.service import AuthorizationService
from nanimai_platform.services.balance.service import (
    BalanceService,
    BalanceServiceBalanceGRPCError,
    BalanceServiceError,
    BalanceServiceInvalidDataError,
)
from nanimai_platform.services.candidate.service import CandidateService
from nanimai_platform.services.llm.service import LLMService
from nanimai_platform.services.project.service import ProjectService
from nanimai_platform.services.vacancy.service import VacancyService

router = APIRouter(tags=["balance"])

log = structlog.stdlib.get_logger("app.router.balance")


@router.get("/tokens")
@inject
async def get_token_balance_handler(
    *,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    balance_service: FromDishka[BalanceService],
    auth_service: FromDishka[AuthorizationService],
) -> BalanceResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        response = await balance_service.get_balance(
            BalanceService.GetBalanceRequest(
                user_id=user.id,
            )
        )
        return BalanceResponseDTO(
            balance_id=response.balance_id,
            user_id=response.user_id,
            current=response.current,
            maximum=response.maximum,
            reserved=response.reserved,
        )
    except BalanceServiceBalanceGRPCError as e:
        log.error(e.log, err=e)
        raise HTTPException(
            status_code=e.http_code,
            detail=e.detail,
        ) from e
    except BalanceServiceInvalidDataError as e:
        log.error("Invalid data in request (or in response)", err=e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except BalanceServiceError as e:
        log.error("Internal server error when getting balance", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("Unable to get balance", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось получить баланс, попробуйте снова спустя некоторое время",
        ) from e


@router.get("/limits")
@inject
async def get_limits_handler(
    *,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    balance_service: FromDishka[BalanceService],
    auth_service: FromDishka[AuthorizationService],
) -> GetManyLimitsResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        response = await balance_service.get_limit_by_user(
            BalanceService.GetLimitByUserRequest(
                user_id=user.id,
            )
        )
        limits = [
            LimitResponseDTO(
                limit_id=limit.limit_id,
                balance_id=limit.balance_id,
                resource_id=limit.resource_id,
                current=limit.current,
                maximum=limit.maximum,
            )
            for limit in response.limits
        ]
        return GetManyLimitsResponseDTO(limits=limits)
    except BalanceServiceBalanceGRPCError as e:
        log.error(e.log, err=e)
        raise HTTPException(
            status_code=e.http_code,
            detail=e.detail,
        ) from e
    except BalanceServiceInvalidDataError as e:
        log.error("Invalid data in request (or in response)", err=e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except BalanceServiceError as e:
        log.error("Internal server error when getting limits", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("Unable to get limits", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось получить лимиты, попробуйте снова спустя некоторое время",
        ) from e


@router.get("/limits/{vacancy_id}")
@inject
async def get_limits_by_vacancy_handler(
    *,
    vacancy_id: VacancyID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    balance_service: FromDishka[BalanceService],
    auth_service: FromDishka[AuthorizationService],
) -> GetSingleLimitResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        response = await balance_service.get_limit_by_vacancy(
            BalanceService.GetLimitByVacancyRequest(
                user_id=user.id,
                vacancy_id=vacancy_id,
            )
        )

        limit_dto = None
        if response.limit_id:  # If limit exists, all fields will be populated
            limit_dto = LimitResponseDTO(
                limit_id=response.limit_id,
                balance_id=response.balance_id,  # type: ignore[arg-type]
                resource_id=response.resource_id,  # type: ignore[arg-type]
                current=response.current,  # type: ignore[arg-type]
                maximum=response.maximum,  # type: ignore[arg-type]
            )

        return GetSingleLimitResponseDTO(limit=limit_dto)
    except BalanceServiceBalanceGRPCError as e:
        log.error(e.log, err=e)
        raise HTTPException(
            status_code=e.http_code,
            detail=e.detail,
        ) from e
    except BalanceServiceInvalidDataError as e:
        log.error("Invalid data in request (or in response)", err=e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except BalanceServiceError as e:
        log.error("Internal server error when getting limits by vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("Unable to get limits by vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось получить лимиты по вакансии, попробуйте снова спустя некоторое время",
        ) from e


@router.post("/limits")
@inject
async def post_limit_handler(
    *,
    request_body: PostLimitRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    balance_service: FromDishka[BalanceService],
    auth_service: FromDishka[AuthorizationService],
) -> LimitResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        response = await balance_service.create_limit(
            BalanceService.CreateLimitRequest(
                user_id=user.id,
                resource_id=request_body.vacancy_id,
                maximum=request_body.maximum,
            )
        )
        return LimitResponseDTO(
            limit_id=response.limit_id,
            balance_id=response.balance_id,
            resource_id=response.resource_id,
            current=response.current,
            maximum=response.maximum,
        )
    except BalanceServiceBalanceGRPCError as e:
        log.error(e.log, err=e)
        raise HTTPException(
            status_code=e.http_code,
            detail=e.detail,
        ) from e
    except BalanceServiceInvalidDataError as e:
        log.error("Invalid data in request (or in response)", err=e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except BalanceServiceError as e:
        log.error("Internal server error when creating limit", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("Unable to creating limit", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось создать лимит, попробуйте снова спустя некоторое время",
        ) from e


@router.put("/limits/{vacancy_id}")
@inject
async def upsert_limit_handler(
    *,
    vacancy_id: VacancyID,
    request_body: UpsertLimitRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    llm_service: FromDishka[LLMService],
    candidate_service: FromDishka[CandidateService],
    balance_service: FromDishka[BalanceService],
    auth_service: FromDishka[AuthorizationService],
) -> LimitResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    is_success = False
    try:
        response = await balance_service.upsert_limit(
            BalanceService.UpsertLimitRequest(
                user_id=user.id,
                resource_id=vacancy_id,
                maximum=request_body.maximum,
            )
        )

        is_success = True
        return LimitResponseDTO(
            limit_id=response.limit_id,
            balance_id=response.balance_id,
            resource_id=response.resource_id,
            current=response.current,
            maximum=response.maximum,
        )
    except BalanceServiceBalanceGRPCError as e:
        log.error(e.log, err=e)
        raise HTTPException(
            status_code=e.http_code,
            detail=e.detail,
        ) from e
    except BalanceServiceInvalidDataError as e:
        log.error("Invalid data in request (or in response)", err=e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except BalanceServiceError as e:
        log.error("Internal server error when updating limit", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("Unable to update limit", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить лимит, попробуйте снова спустя некоторое время",
        ) from e
    finally:

        async def try_schedule_all_rejected_candidates():
            # Этот код написан пьяным техлидом в 3 часа ночи, просьба не ругаться
            #
            # todo: переписать это плохое и нехорошее нечто на нормальную архитектуру
            all_candidates = await candidate_service.read_many_candidate_cards(
                CandidateService.ReadManyCandidateCardsRequest(vacancy_id=vacancy_id)
            )
            for candidate in all_candidates:
                if candidate.analysis_status == CandidateAnalysisStatusEnum.REJECTED:
                    try:
                        _ = await llm_service.new_analyze_operation(
                            LLMService.NewAnalyzeOperationRequest(
                                user_id=user.id,
                                candidate_id=candidate.id,
                                vacancy_id=vacancy_id,
                            )
                        )
                    except Exception:
                        pass

        if is_success:
            _ = asyncio.create_task(try_schedule_all_rejected_candidates())


# Этот код написан пьяным техлидом в 3 часа ночи, просьба не ругаться
@router.post("/balance/topup_hooks")
@inject
async def topup_hooks(
    *,
    vacancy_id: VacancyID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    llm_service: FromDishka[LLMService],
    candidate_service: FromDishka[CandidateService],
    auth_service: FromDishka[AuthorizationService],
    project_service: FromDishka[ProjectService],
    vacancy_service: FromDishka[VacancyService],
):
    user = await authorized.get_current_user(credentials, auth_service)

    ops = []

    for project in await project_service.read_many_by_user(ProjectService.ReadManyByUserRequest(user_id=user.id)):
        for vacancy in await vacancy_service.read_many_by_project(
            VacancyService.ReadManyByProjectRequest(project_id=project.id)
        ):
            for candidate in await candidate_service.read_many_candidate_cards(
                CandidateService.ReadManyCandidateCardsRequest(vacancy_id=vacancy.id)
            ):
                try:
                    op = await llm_service.new_analyze_operation(
                        LLMService.NewAnalyzeOperationRequest(
                            user_id=user.id, vacancy_id=vacancy.id, candidate_id=candidate.id
                        )
                    )
                except Exception as e:
                    log.error("failed to create analyze operation on top-up trigger", err=e)
                    ops.append({"id": None, "status": "failed"})
                else:
                    ops.append({"id": str(op), "status": "success"})

    return ops
