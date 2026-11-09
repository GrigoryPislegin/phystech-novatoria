from typing import Annotated

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nanimai_platform.cmd.server.api.v1.hook.dto import (
    RebalanceVacancyCandidateRequestDTO,
)
from nanimai_platform.cmd.server.dependencies import authorized
from nanimai_platform.services.authorization.service import AuthorizationService
from nanimai_platform.services.candidate.rebalance_vacancy_candidates_hook import (
    RebalanceVacancyCandidatesHook,
    RebalanceVacancyCandidatesHookCandidateNotFoundError,
    RebalanceVacancyCandidatesHookError,
    RebalanceVacancyCandidatesHookInvalidDataError,
    RebalanceVacancyCandidatesHookVacancyNotFoundError,
)

router = APIRouter(tags=["hook"])

log = structlog.stdlib.get_logger("app.router.hook")


@router.post("/rebalance_vacancy_candidates")
@inject
async def post_rebalance_vacancy_candidates_hook(
    *,
    request: RebalanceVacancyCandidateRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    rebalance_vacancy_candidates_hook: FromDishka[RebalanceVacancyCandidatesHook],
    auth_service: FromDishka[AuthorizationService],
) -> dict[str, str]:
    _ = await authorized.get_current_user(credentials, auth_service)
    try:
        _ = await rebalance_vacancy_candidates_hook.rebalance_vacancy_candidates(
            RebalanceVacancyCandidatesHook.RebalanceVacancyCandidates(
                vacancy_id=request.vacancy_id,
                new_threshold=request.new_threshold,
            )
        )
        return {"status": "success"}
    except RebalanceVacancyCandidatesHookInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except RebalanceVacancyCandidatesHookCandidateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Кандидат не найден, попробуйте перезагрузить страницу",
        ) from e
    except RebalanceVacancyCandidatesHookVacancyNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вакансия не найдена, попробуйте перезагрузить страницу",
        ) from e
    except RebalanceVacancyCandidatesHookError as e:
        log.error("Internal server error when getting scoring candidate", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("Unable to use hook", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
