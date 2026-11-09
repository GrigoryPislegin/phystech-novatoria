from typing import Annotated

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Form, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nanimai_platform.cmd.server.api.v2.llm.dto import (
    CriterionPayloadResponseDTO,
    GetManyCriterionPayloadsResponseDTO,
    ParseVacancyFormRequestDTO,
    ParseVacancyRequestDTO,
    ParseVacancyResponseDTO,
)
from nanimai_platform.cmd.server.dependencies import authorized
from nanimai_platform.domain import SalaryAmountRange, Skill, VacancyStageStatus
from nanimai_platform.services.authorization import AuthorizationService
from nanimai_platform.services.llm import LLMService, LLMServiceError, LLMServiceTulpaGRPCError

router = APIRouter(tags=["llm_v2"])

log = structlog.stdlib.get_logger("app.router.llm")


@router.post("/parse-vacancy")
@inject
async def post_parse_vacancy_handler(
    *,
    data: Annotated[ParseVacancyFormRequestDTO, Form()],
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    llm_service: FromDishka[LLMService],
    auth_service: FromDishka[AuthorizationService],
) -> ParseVacancyResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        vacancy = await llm_service.parse_vacancy(
            LLMService.ParseVacancyRequest(
                user_id=user.id,
                project_id=data.project_id,
                file=await data.file.read(),
            )
        )
        return ParseVacancyResponseDTO.from_domain(vacancy)
    except LLMServiceTulpaGRPCError as e:
        log.error(e.log, err=e)
        raise HTTPException(
            status_code=e.http_code,
            detail=e.detail,
        ) from e
    except LLMServiceError as e:
        log.error("failed to parse vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("failed to parse vacancy", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось создать критерии, попробуйте снова спустя некоторое время",
        ) from e


@router.post("/generate-criteria")
@inject
async def post_many_generative_criteria_by_vacancy_handler(
    *,
    data: ParseVacancyRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    llm_service: FromDishka[LLMService],
    auth_service: FromDishka[AuthorizationService],
) -> GetManyCriterionPayloadsResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        criterion_payloads = await llm_service.generate_vacancy_criteria(
            LLMService.GenerateVacancyCriteriaRequest(
                user_id=user.id,
                project_id=data.project_id,
                title=data.title,
                description=data.description,
                specialization=data.specialization,
                status=data.status,
                city=data.city,
                country=data.country,
                hire_amount=data.hire_amount,
                salary=SalaryAmountRange(
                    currency=data.salary.currency,  # type: ignore[arg-type]
                    min=data.salary.min,
                    max=data.salary.max,
                )
                if data.salary is not None
                else None,
                work_type=data.work_type,
                work_format=data.work_format,
                is_internship=data.is_internship,
                is_temphire=data.is_temphire,
                schedule=data.schedule,
                daily_rate=data.daily_rate,
                experience=data.experience,
                skills=[Skill(title=skill) for skill in data.skills],
                stages=[VacancyStageStatus(stage=stage.kind, shown=stage.shown) for stage in data.stages]
                if data.stages is not None
                else None,
            )
        )

        response = []
        for criterion_payload in criterion_payloads:
            response.append(CriterionPayloadResponseDTO.from_domain(criterion_payload))

        return GetManyCriterionPayloadsResponseDTO(criterion_payloads=response)

    except LLMServiceTulpaGRPCError as e:
        log.error(e.log, err=e)
        raise HTTPException(
            status_code=e.http_code,
            detail=e.detail,
        ) from e
    except LLMServiceError as e:
        log.error("failed to generate criteria", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("failed to generate criteria", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось создать критерии, попробуйте снова спустя некоторое время",
        ) from e
