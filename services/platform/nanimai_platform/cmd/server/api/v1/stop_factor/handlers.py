from typing import Annotated

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nanimai_platform.cmd.server.api.v1.stop_factor.dto import (
    GetManyStopFactorsResponseDTO,
    PostStopFactorRequestDTO,
    PutStopFactorRequestDTO,
    StopFactorResponseDTO,
)
from nanimai_platform.cmd.server.dependencies import authorized
from nanimai_platform.domain import StopFactorID, VacancyID
from nanimai_platform.services import AuthorizationService, VacancyService
from nanimai_platform.services.stop_factor.service import (
    StopFactorService,
    StopFactorServiceError,
    StopFactorServiceInvalidDataError,
    StopFactorServiceStopFactorNotFoundError,
    StopFactorServiceVacancyNotFoundError,
)
from nanimai_platform.services.vacancy import VacancyServiceError

router = APIRouter(tags=["stop_factors"])

log = structlog.stdlib.get_logger("app.router.stop_factors")


@router.get("/vacancy/{vacancy_id}")
@inject
async def get_many_stop_factors_by_vacancy_handler(
    *,
    vacancy_id: VacancyID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    stop_factor_service: FromDishka[StopFactorService],
    auth_service: FromDishka[AuthorizationService],
) -> GetManyStopFactorsResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        stop_factors = await stop_factor_service.read_many_by_vacancy(
            StopFactorService.ReadManyStopFactorsByVacancyRequest(vacancy_id=vacancy_id),
        )
        response = []
        for stop_factor in stop_factors:
            response.append(
                StopFactorResponseDTO(
                    id=stop_factor.id,
                    created_at=stop_factor.created_at,
                    updated_at=stop_factor.updated_at,
                    user_id=stop_factor.user_id,
                    project_id=stop_factor.project_id,
                    vacancy_id=stop_factor.vacancy_id,
                    stop_factor=stop_factor.stop_factor,
                    initial_weight=stop_factor.initial_weight,
                )
            )
        return GetManyStopFactorsResponseDTO(stop_factors=response)
    except StopFactorServiceVacancyNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вакансия не найдена, попробуйте перезагрузить страницу",
        ) from e
    except StopFactorServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except StopFactorServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось получить стоп-факторы, попробуйте снова спустя некоторое время",
        ) from e


@router.get("/{stop_factor_id}")
@inject
async def get_stop_factor_handler(
    *,
    stop_factor_id: StopFactorID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    stop_factor_service: FromDishka[StopFactorService],
    auth_service: FromDishka[AuthorizationService],
) -> StopFactorResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        stop_factor = await stop_factor_service.read(
            StopFactorService.ReadStopFactorRequest(id=stop_factor_id),
        )
        return StopFactorResponseDTO(
            id=stop_factor.id,
            created_at=stop_factor.created_at,
            updated_at=stop_factor.updated_at,
            user_id=stop_factor.user_id,
            project_id=stop_factor.project_id,
            vacancy_id=stop_factor.vacancy_id,
            stop_factor=stop_factor.stop_factor,
            initial_weight=stop_factor.initial_weight,
        )
    except StopFactorServiceStopFactorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Стоп-фактор не найден, попробуйте перезагрузить страницу",
        ) from e
    except StopFactorServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except StopFactorServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось создать критерий, попробуйте снова спустя некоторое время",
        ) from e


@router.post("/")
@inject
async def post_stop_factor_handler(
    *,
    request_body: PostStopFactorRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    vacancy_service: FromDishka[VacancyService],
    stop_factor_service: FromDishka[StopFactorService],
    auth_service: FromDishka[AuthorizationService],
) -> StopFactorResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        vacancy = await vacancy_service.read(VacancyService.ReadVacancyRequest(id=request_body.vacancy_id))

        stop_factor = await stop_factor_service.create(
            StopFactorService.CreateStopFactorRequest(
                user_id=user.id,
                project_id=vacancy.project_id,
                vacancy_id=vacancy.id,
                stop_factor=request_body.stop_factor,
                initial_weight=request_body.initial_weight,
            )
        )

        return StopFactorResponseDTO(
            id=stop_factor.id,
            created_at=stop_factor.created_at,
            updated_at=stop_factor.updated_at,
            user_id=stop_factor.user_id,
            project_id=stop_factor.project_id,
            vacancy_id=stop_factor.vacancy_id,
            stop_factor=stop_factor.stop_factor,
            initial_weight=stop_factor.initial_weight,
        )
    except VacancyServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вакансия не найдена, попробуйте перезагрузить страницу",
        ) from e
    except StopFactorServiceVacancyNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вакансия не найдена, попробуйте перезагрузить страницу",
        ) from e
    except StopFactorServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except StopFactorServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось создать стоп-фактор, попробуйте снова спустя некоторое время",
        ) from e


@router.put("/{stop_factor_id}/")
@inject
async def put_stop_factor_handler(
    *,
    stop_factor_id: StopFactorID,
    request_body: PutStopFactorRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    stop_factor_service: FromDishka[StopFactorService],
    auth_service: FromDishka[AuthorizationService],
) -> StopFactorResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        stop_factor = await stop_factor_service.update(
            StopFactorService.UpdateStopFactorRequest(
                id=stop_factor_id,
                stop_factor=request_body.stop_factor,
                initial_weight=request_body.initial_weight,
            )
        )
        return StopFactorResponseDTO(
            id=stop_factor.id,
            created_at=stop_factor.created_at,
            updated_at=stop_factor.updated_at,
            user_id=stop_factor.user_id,
            project_id=stop_factor.project_id,
            vacancy_id=stop_factor.vacancy_id,
            stop_factor=stop_factor.stop_factor,
            initial_weight=stop_factor.initial_weight,
        )
    except StopFactorServiceStopFactorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Стоп-фактор не найден, попробуйте перезагрузить страницу",
        ) from e
    except StopFactorServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except StopFactorServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить стоп-фактор, попробуйте снова спустя некоторое время",
        ) from e


@router.delete("/{stop_factor_id}")
@inject
async def delete_stop_factor_handler(
    *,
    stop_factor_id: StopFactorID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    stop_factor_service: FromDishka[StopFactorService],
    auth_service: FromDishka[AuthorizationService],
) -> StopFactorResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        stop_factor = await stop_factor_service.delete(
            StopFactorService.DeleteStopFactorRequest(id=stop_factor_id),
        )
        return StopFactorResponseDTO(
            id=stop_factor.id,
            created_at=stop_factor.created_at,
            updated_at=stop_factor.updated_at,
            user_id=stop_factor.user_id,
            project_id=stop_factor.project_id,
            vacancy_id=stop_factor.vacancy_id,
            stop_factor=stop_factor.stop_factor,
            initial_weight=stop_factor.initial_weight,
        )
    except StopFactorServiceStopFactorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Стоп-фактор не найден, попробуйте перезагрузить страницу",
        ) from e
    except StopFactorServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except StopFactorServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось удалить стоп-фактор, попробуйте снова спустя некоторое время",
        ) from e
