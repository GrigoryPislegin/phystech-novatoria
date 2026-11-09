from typing import override

from nanimai_platform.adapters.external.skill_recommendations.constant_skill_recommendation.job_skill_mapped import (
    job_skills_mapped,
)
from nanimai_platform.protocols.external.skill_recommendations import (
    SkillRecommendationError,
    SkillRecommendationProtocol,
    SkillRecommendationRequest,
    SkillRecommendationResponse,
    SkillsRecommendationsNotFound,
)


class ConstantSkillRecommendationAdapter(SkillRecommendationProtocol):
    @override
    def recommend(self, request: SkillRecommendationRequest) -> SkillRecommendationResponse:
        try:
            job_list = job_skills_mapped.get(request.job_sphere, {})
            skills = job_list.get(request.job_name, [])
        except Exception as e:
            raise SkillRecommendationError("Constant Skill Recommendation adapter failed") from e
        if skills == []:
            raise SkillsRecommendationsNotFound("Job sphere or job not found")
        return SkillRecommendationResponse(skills=skills)
