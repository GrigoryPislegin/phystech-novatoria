from typing import final

import structlog

from nanimai_platform.protocols.external.skill_recommendations import (
    SkillRecommendationError,
    SkillRecommendationProtocol,
    SkillRecommendationRequest,
    SkillRecommendationResponse,
    SkillsRecommendationsNotFound,
)
from nanimai_platform.utils.logging_span import span

log = structlog.stdlib.get_logger("app.service.RecommendSkillsForVacancyService")


@final
class SkillsService:
    def __init__(self, skill_adapter: SkillRecommendationProtocol):
        self.recommendation_adapter = skill_adapter

    @span(op="skills_service", name="recommend")
    def recommend(self, request: SkillRecommendationRequest) -> SkillRecommendationResponse:
        try:
            skills = self.recommendation_adapter.recommend(request)
        except SkillsRecommendationsNotFound as e:
            log.info(f"Skills not found for {request.job_sphere} and {request.job_name}")
            raise e
        except SkillRecommendationError as e:
            log.error(f"Service failed with data {request.job_sphere} and {request.job_name}")
            raise e
        return skills
