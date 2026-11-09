from typing import Annotated

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Form, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nanimai_platform import services
from nanimai_platform.cmd.server.dependencies import authorized
from nanimai_platform.services.authorization.service import AuthorizationService
from nanimai_platform.services.llm.service import LLMService

from .dto import (
    AnalyzeMultipleCandidateForVacancyRequestDTO,
    AnalyzeMultipleCandidateForVacancyResponseDTO,
    AnalyzeSingleCandidateForVacancyRequestDTO,
    AnalyzeSingleCandidateForVacancyResponseDTO,
    ErrorDTO,
    OperationDTO,
    ParseCandidatesFormRequestDTO,
    ParseMultipleCandidateResponseDTO,
)

router = APIRouter(tags=["llm"])

log = structlog.stdlib.get_logger("app.router.llm")


@router.post("/parse-candidate")
@inject
async def post_parse_candidate_handler(
    request_body: Annotated[ParseCandidatesFormRequestDTO, Form()],
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    llm_service: FromDishka[LLMService],
    auth_service: FromDishka[AuthorizationService],
) -> ParseMultipleCandidateResponseDTO:
    log.debug("received post parse candidate request")
    user = await authorized.get_current_user(credentials, auth_service)
    ops: list[OperationDTO | ErrorDTO] = []
    for file in request_body.files:
        try:
            operation_id = await llm_service.parse_candidate(
                LLMService.ParseCandidateRequest(
                    user_id=user.id,
                    vacancy_id=request_body.vacancy_id,
                    file=await file.read(),
                )
            )
            ops.append(OperationDTO(id=operation_id))
        except Exception as e:
            log.error("failed to create parse candidate operation", err=e)
            ops.append(ErrorDTO(message=str(e)))

    return ParseMultipleCandidateResponseDTO(ops=ops)


@router.post("/analysis/single")
@inject
async def post_analysis_handler(
    data: AnalyzeSingleCandidateForVacancyRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    llm_service: FromDishka[LLMService],
    auth_service: FromDishka[AuthorizationService],
) -> AnalyzeSingleCandidateForVacancyResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        operation_id = await llm_service.new_analyze_operation(
            LLMService.NewAnalyzeOperationRequest(
                user_id=user.id, candidate_id=data.candidate_id, vacancy_id=data.vacancy_id
            )
        )
        return AnalyzeSingleCandidateForVacancyResponseDTO(op_id=operation_id)
    except services.llm.LLMServiceTargetNotFoundError as e:
        log.error("failed to create operation with error: target not found", err=e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Цель для анализа не найдена, проверьте корректность данных и попробуйте снова",
        ) from e
    except services.llm.LLMServiceOperationCreationError as e:
        log.error("failed to create operation with error: internal server error", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось создать операцию анализа, попробуйте снова спустя некоторое время",
        ) from e
    except services.llm.LLMServiceJobQueueError as e:
        log.error("failed to create operation with error: job queue error", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка очереди заданий, попробуйте снова спустя некоторое время",
        ) from e
    except (services.llm.LLMServiceTulpaGRPCError, services.llm.LLMServiceBalanceGRPCError) as e:
        log.error(e.log, err=e)
        raise HTTPException(
            status_code=e.http_code,
            detail=e.detail,
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e


@router.post("/analysis/multiple")
@inject
async def post_multiple_analysis_handler(
    data: AnalyzeMultipleCandidateForVacancyRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    llm_service: FromDishka[LLMService],
    auth_service: FromDishka[AuthorizationService],
) -> AnalyzeMultipleCandidateForVacancyResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    ops: list[OperationDTO | ErrorDTO] = []
    for candidate_id in data.candidate_ids:
        try:
            operation_id = await llm_service.new_analyze_operation(
                LLMService.NewAnalyzeOperationRequest(
                    user_id=user.id, candidate_id=candidate_id, vacancy_id=data.vacancy_id
                )
            )
            ops.append(OperationDTO(id=operation_id))
        except services.LLMServiceTariffError as e:
            log.error("failed to create operation with error: tariff exceeded", err=e)
            ops.append(ErrorDTO(message="Вы превысили лимит количества анализов"))
        except services.llm.LLMServiceTargetNotFoundError as e:
            log.error("failed to create operation with error: target not found", err=e)
            ops.append(
                ErrorDTO(message="Цель для анализа не найдена, проверьте корректность данных и попробуйте снова")
            )
        except services.llm.LLMServiceOperationCreationError as e:
            log.error("failed to create operation with error: internal server error", err=e)
            ops.append(ErrorDTO(message="Не удалось создать операцию анализа, попробуйте снова спустя некоторое время"))
        except services.llm.LLMServiceJobQueueError as e:
            log.error("failed to create operation with error: job queue error", err=e)
            ops.append(ErrorDTO(message="Ошибка очереди заданий, попробуйте снова спустя некоторое время"))
        except (services.llm.LLMServiceTulpaGRPCError, services.llm.LLMServiceBalanceGRPCError) as e:
            log.error(e.log, err=e)
            ops.append(ErrorDTO(message=e.detail))
        except Exception:
            ops.append(ErrorDTO(message="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время"))

    return AnalyzeMultipleCandidateForVacancyResponseDTO(ops=ops)
