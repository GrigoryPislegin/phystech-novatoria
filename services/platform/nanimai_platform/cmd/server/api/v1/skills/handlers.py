from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nanimai_platform.cmd.server.api.v1.skills.dto import SkillRecommendationRequestDTO, SkillRecommendationResponseDTO
from nanimai_platform.cmd.server.dependencies import authorized
from nanimai_platform.protocols.external.skill_recommendations import (
    SkillRecommendationError,
    SkillRecommendationRequest,
    SkillsRecommendationsNotFound,
)
from nanimai_platform.services import SkillsService
from nanimai_platform.services.authorization.service import AuthorizationService

router = APIRouter(tags=["skills"])


@router.get(
    "/",
    response_model=SkillRecommendationResponseDTO,
    response_model_exclude_unset=True,
)
@inject
async def get_recommendations_handler(
    *,
    request: Annotated[SkillRecommendationRequestDTO, Query()],
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    skill_service: FromDishka[SkillsService],
    auth_service: FromDishka[AuthorizationService],
) -> SkillRecommendationResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    _ = user
    try:
        response = skill_service.recommend(
            SkillRecommendationRequest(
                job_sphere=request.job_sphere,
                job_name=request.job_name,
            )
        )
    except SkillsRecommendationsNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job sphere or job not found") from e
    except SkillRecommendationError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) from e
    return SkillRecommendationResponseDTO(skills=response.skills)
