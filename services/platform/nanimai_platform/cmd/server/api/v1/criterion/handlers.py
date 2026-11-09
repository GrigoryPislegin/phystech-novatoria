from typing import Annotated

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nanimai_platform.cmd.server.api.v1.criterion.dto import (
    CriterionResponseDTO,
    GetManyCriteriaResponseDTO,
    PostCriterionRequestDTO,
    PutCriterionRequestDTO,
)
from nanimai_platform.cmd.server.dependencies import authorized
from nanimai_platform.domain import CriterionID, VacancyID
from nanimai_platform.services import AuthorizationService, VacancyService
from nanimai_platform.services.criterion.service import (
    CriterionService,
    CriterionServiceCriterionNotFoundError,
    CriterionServiceError,
    CriterionServiceInvalidDataError,
    CriterionServiceVacancyNotFoundError,
)
from nanimai_platform.services.vacancy import VacancyServiceError

router = APIRouter(tags=["criteria"])

log = structlog.stdlib.get_logger("app.router.criteria")


@router.get("/vacancy/{vacancy_id}")
@inject
async def get_many_criteria_by_vacancy_handler(
    *,
    vacancy_id: VacancyID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    criterion_service: FromDishka[CriterionService],
    auth_service: FromDishka[AuthorizationService],
) -> GetManyCriteriaResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        criteria = await criterion_service.read_many_by_vacancy(
            CriterionService.ReadManyCriteriaByVacancyRequest(vacancy_id=vacancy_id),
        )
        response = []
        for criterion in criteria:
            response.append(
                CriterionResponseDTO(
                    id=criterion.id,
                    created_at=criterion.created_at,
                    updated_at=criterion.updated_at,
                    user_id=criterion.user_id,
                    project_id=criterion.project_id,
                    vacancy_id=criterion.vacancy_id,
                    criterion=criterion.criterion,
                    initial_weight=criterion.initial_weight,
                    weight=criterion.weight,
                )
            )
        return GetManyCriteriaResponseDTO(criteria=response)
    except CriterionServiceVacancyNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вакансия не найдена, попробуйте перезагрузить страницу",
        ) from e
    except CriterionServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except CriterionServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось получить критерии, попробуйте снова спустя некоторое время",
        ) from e


@router.get("/{criterion_id}")
@inject
async def get_criterion_handler(
    *,
    criterion_id: CriterionID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    criterion_service: FromDishka[CriterionService],
    auth_service: FromDishka[AuthorizationService],
) -> CriterionResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        criterion = await criterion_service.read(
            CriterionService.ReadCriterionRequest(id=criterion_id),
        )
        return CriterionResponseDTO(
            id=criterion.id,
            created_at=criterion.created_at,
            updated_at=criterion.updated_at,
            user_id=criterion.user_id,
            project_id=criterion.project_id,
            vacancy_id=criterion.vacancy_id,
            criterion=criterion.criterion,
            initial_weight=criterion.initial_weight,
            weight=criterion.weight,
        )
    except CriterionServiceCriterionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Критерий не найден, попробуйте перезагрузить страницу",
        ) from e
    except CriterionServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except CriterionServiceError as e:
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
async def post_criterion_handler(
    *,
    request_body: PostCriterionRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    criterion_service: FromDishka[CriterionService],
    auth_service: FromDishka[AuthorizationService],
    vacancy_service: FromDishka[VacancyService],
) -> CriterionResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        vacancy = await vacancy_service.read(VacancyService.ReadVacancyRequest(id=request_body.vacancy_id))

        criterion = await criterion_service.create(
            CriterionService.CreateCriterionRequest(
                user_id=user.id,
                project_id=vacancy.project_id,
                vacancy_id=vacancy.id,
                criterion=request_body.criterion,
                initial_weight=request_body.initial_weight,
            )
        )

        return CriterionResponseDTO(
            id=criterion.id,
            created_at=criterion.created_at,
            updated_at=criterion.updated_at,
            user_id=criterion.user_id,
            project_id=criterion.project_id,
            vacancy_id=criterion.vacancy_id,
            criterion=criterion.criterion,
            initial_weight=criterion.initial_weight,
            weight=criterion.weight,
        )
    except VacancyServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вакансия не найдена, попробуйте перезагрузить страницу",
        ) from e
    except CriterionServiceVacancyNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вакансия не найдена, попробуйте перезагрузить страницу",
        ) from e
    except CriterionServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except CriterionServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось создать критерий, попробуйте снова спустя некоторое время",
        ) from e


@router.put("/{criterion_id}/")
@inject
async def put_criterion_handler(
    *,
    criterion_id: CriterionID,
    request_body: PutCriterionRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    criterion_service: FromDishka[CriterionService],
    auth_service: FromDishka[AuthorizationService],
) -> CriterionResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        criterion = await criterion_service.update(
            CriterionService.UpdateCriterionRequest(
                id=criterion_id,
                criterion=request_body.criterion,
                initial_weight=request_body.initial_weight,
            )
        )
        return CriterionResponseDTO(
            id=criterion.id,
            created_at=criterion.created_at,
            updated_at=criterion.updated_at,
            user_id=criterion.user_id,
            project_id=criterion.project_id,
            vacancy_id=criterion.vacancy_id,
            criterion=criterion.criterion,
            initial_weight=criterion.initial_weight,
            weight=criterion.weight,
        )
    except CriterionServiceCriterionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Критерий не найден, попробуйте перезагрузить страницу",
        ) from e
    except CriterionServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except CriterionServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить критерий, попробуйте снова спустя некоторое время",
        ) from e


@router.delete("/{criterion_id}")
@inject
async def delete_criterion_handler(
    *,
    criterion_id: CriterionID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    criterion_service: FromDishka[CriterionService],
    auth_service: FromDishka[AuthorizationService],
) -> CriterionResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        criterion = await criterion_service.delete(
            CriterionService.DeleteCriterionRequest(id=criterion_id),
        )
        return CriterionResponseDTO(
            id=criterion.id,
            created_at=criterion.created_at,
            updated_at=criterion.updated_at,
            user_id=criterion.user_id,
            project_id=criterion.project_id,
            vacancy_id=criterion.vacancy_id,
            criterion=criterion.criterion,
            initial_weight=criterion.initial_weight,
            weight=criterion.weight,
        )
    except CriterionServiceCriterionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Критерий не найден, попробуйте перезагрузить страницу",
        ) from e
    except CriterionServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except CriterionServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось удалить критерий, попробуйте снова спустя некоторое время",
        ) from e
