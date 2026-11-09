from typing import Annotated

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nanimai_platform.cmd.server.api.v2.candidate.dto import (
    CandidateCardCriterionAnalysisDTO,
    CandidateCardDTO,
    CandidateCardExpectedSalaryDTO,
    GetAllCandidateCardsResponseDTO,
    StopFactorAnalysisDTO,
)
from nanimai_platform.cmd.server.dependencies import authorized
from nanimai_platform.domain.scalar.scalars import VacancyID
from nanimai_platform.services.authorization.service import AuthorizationService
from nanimai_platform.services.candidate.service import (
    CandidateService,
    CandidateServiceError,
    CandidateServiceInvalidDataError,
)

router = APIRouter(tags=["candidate"])

log = structlog.stdlib.get_logger("app.router.candidate")


@router.get("/")
@inject
async def get_all_candidates_handler(
    *,
    vacancy_id: VacancyID,
    resume: str | None = None,
    name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    city: str | None = None,
    country: str | None = None,
    notes: str | None = None,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    candidate_service: FromDishka[CandidateService],
    auth_service: FromDishka[AuthorizationService],
) -> GetAllCandidateCardsResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)

    try:
        cards = await candidate_service.read_many_candidate_cards(
            CandidateService.ReadManyCandidateCardsRequest(
                vacancy_id=vacancy_id,
                resume=resume,
                name=name,
                phone=phone,
                email=email,
                city=city,
                country=country,
                notes=notes,
            )
        )
        response = []
        for card in cards:
            response.append(
                CandidateCardDTO(
                    id=card.id,
                    user_id=card.user_id,
                    project_id=card.project_id,
                    vacancy_id=card.vacancy_id,
                    created_at=card.created_at,
                    updated_at=card.updated_at,
                    name=card.name,
                    experience=card.experience,
                    expected_salary=CandidateCardExpectedSalaryDTO(
                        currency=card.expected_salary.currency,
                        value=card.expected_salary.value,
                    )
                    if card.expected_salary is not None
                    else None,
                    thumbnail_url=card.thumbnail_url,
                    source=card.source,
                    status=card.status,
                    notes_preview=card.notes_preview,
                    dirty=card.dirty,
                    score=card.score,
                    analysis_id=card.analysis_id,
                    criteria={
                        id: CandidateCardCriterionAnalysisDTO(
                            score=value.score, status=value.status, description=value.description
                        )
                        for id, value in card.criteria.items()
                    }
                    if card.criteria
                    else {},
                    stop_factors={
                        id: StopFactorAnalysisDTO(status=value.status, description=value.description)
                        for id, value in card.stop_factors.items()
                    }
                    if card.stop_factors
                    else {},
                    contacts=card.contacts,
                )
            )

        return GetAllCandidateCardsResponseDTO(candidates=response)
    except CandidateServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="При попытке загрузить кандидатов были переданы неверные данные, попробуйте перезагрузить страницу",
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
