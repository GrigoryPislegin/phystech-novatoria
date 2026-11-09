from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nanimai_platform.cmd.server.api.v1.operation.dto import (
    GenerateAnalysisOperationResponseDTO,
    GetAllOperationsResponseDTO,
    OperationAnalysisDTO,
    OperationCandidateDTO,
    OperationProjectDTO,
    OperationVacancyDTO,
    ParseCandidateOperationResponseDTO,
    ParseVacancyOperationResponseDTO,
)
from nanimai_platform.cmd.server.dependencies import authorized
from nanimai_platform.domain import OperationID
from nanimai_platform.domain.operation.operation import Operation, OperationKind
from nanimai_platform.services.authorization.service import AuthorizationService
from nanimai_platform.services.candidate.service import CandidateService, CandidateServiceError
from nanimai_platform.services.operation.service import (
    OperationService,
    OperationServiceError,
    OperationServiceInvalidDataError,
)
from nanimai_platform.services.project.service import ProjectService, ProjectServiceError
from nanimai_platform.services.vacancy.service import VacancyService, VacancyServiceError

router = APIRouter(tags=["operation"])

log = structlog.stdlib.get_logger("app.api.v1.operation.handlers")


async def operation_to_dto(
    operation: Operation,
    project_service: ProjectService,
    vacancy_service: VacancyService,
    candidate_service: CandidateService,
):
    if operation.kind == OperationKind.PARSE_VACANCY:
        project = await project_service.read(ProjectService.ReadProjectRequest(id=operation.project_id))

        if operation.created_vacancy_id is not None:
            vacancy = await vacancy_service.read(VacancyService.ReadVacancyRequest(id=operation.created_vacancy_id))
        else:
            vacancy = None

        return ParseVacancyOperationResponseDTO(
            id=operation.id,
            created_at=operation.created_at,
            status=operation.status,
            finished_at=operation.finished_at,
            project=OperationProjectDTO(
                id=project.id,
                title=project.title,
            ),
            created_vacancy=OperationVacancyDTO(
                id=vacancy.id,
                title=vacancy.title,
            )
            if vacancy is not None
            else None,
        )

    elif operation.kind == OperationKind.PARSE_CANDIDATE:
        vacancy = await vacancy_service.read(VacancyService.ReadVacancyRequest(id=operation.vacancy_id))

        if operation.created_candidate_id is not None:
            candidate = await candidate_service.read(
                CandidateService.ReadCandidateRequest(id=operation.created_candidate_id)
            )
        else:
            candidate = None

        return ParseCandidateOperationResponseDTO(
            id=operation.id,
            created_at=operation.created_at,
            status=operation.status,
            finished_at=operation.finished_at,
            vacancy=OperationVacancyDTO(
                id=vacancy.id,
                title=vacancy.title,
            ),
            created_candidate=OperationCandidateDTO(
                id=candidate.id,
                name=candidate.name,
            )
            if candidate is not None
            else None,
        )
    elif operation.kind == OperationKind.GENERATE_ANALYSIS:
        candidate = await candidate_service.read(CandidateService.ReadCandidateRequest(id=operation.candidate_id))
        vacancy = await vacancy_service.read(VacancyService.ReadVacancyRequest(id=candidate.vacancy_id))
        analysis = None

        return GenerateAnalysisOperationResponseDTO(
            id=operation.id,
            created_at=operation.created_at,
            status=operation.status,
            finished_at=operation.finished_at,
            vacancy=OperationVacancyDTO(
                id=vacancy.id,
                title=vacancy.title,
            ),
            candidate=OperationCandidateDTO(id=candidate.id, name=candidate.name),
            created_analysis=OperationAnalysisDTO(
                id=analysis.id,
                score=analysis.score,
            )
            if analysis is not None
            else None,
        )


@router.get("/{operation_id}")
@inject
async def get_operation_handler(
    *,
    operation_id: OperationID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    operation_service: FromDishka[OperationService],
    project_service: FromDishka[ProjectService],
    vacancy_service: FromDishka[VacancyService],
    candidate_service: FromDishka[CandidateService],
    auth_service: FromDishka[AuthorizationService],
) -> ParseVacancyOperationResponseDTO | ParseCandidateOperationResponseDTO | GenerateAnalysisOperationResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        _ = user
        operation = await operation_service.read(OperationService.ReadOperationRequest(id=operation_id))

        return await operation_to_dto(operation, project_service, vacancy_service, candidate_service)
    except (
        OperationServiceError,
        ProjectServiceError,
        VacancyServiceError,
        CandidateServiceError,
    ) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Операция или ее компоненты не найдены, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("unable to read operation", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось получить операцию, попробуйте снова спустя некоторое время",
        ) from e


@router.get("/")
@inject
async def get_all_operations(
    *,
    period: Literal["1h", "30m", "10m", "1m"],
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    operation_service: FromDishka[OperationService],
    project_service: FromDishka[ProjectService],
    vacancy_service: FromDishka[VacancyService],
    candidate_service: FromDishka[CandidateService],
    auth_service: FromDishka[AuthorizationService],
) -> GetAllOperationsResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        now = datetime.now(UTC)

        if period == "1h":
            delta = timedelta(hours=1)
        elif period == "30m":
            delta = timedelta(minutes=30)
        elif period == "10m":
            delta = timedelta(minutes=10)
        elif period == "1m":
            delta = timedelta(minutes=1)
        else:
            log.warn("unhandled period", period=period)
            delta = datetime.now(UTC) - datetime.min

        operations = await operation_service.read_many_by_user(OperationService.ReadManyByUserRequest(user_id=user.id))
        dtos = []
        for operation in operations:
            if operation.created_at.replace(tzinfo=UTC) < (now - delta).replace(tzinfo=UTC):
                continue

            dtos.append(
                await operation_to_dto(
                    operation,
                    project_service=project_service,
                    vacancy_service=vacancy_service,
                    candidate_service=candidate_service,
                )
            )

        return GetAllOperationsResponseDTO(operations=dtos)
    except OperationServiceInvalidDataError as e:
        log.error("invalid data in request", err=e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except OperationServiceError as e:
        log.error("internal service error", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("unable to read operations", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось получить список операций, попробуйте снова спустя некоторое время",
        ) from e
