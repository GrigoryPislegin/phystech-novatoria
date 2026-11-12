from abc import ABC, abstractmethod

from pydantic import BaseModel


class SkillRecommendationRequest(BaseModel):
    job_sphere: str
    job_name: str


class SkillRecommendationResponse(BaseModel):
    skills: list[str]


class SkillRecommendationError(Exception): ...


class SkillsRecommendationsNotFound(SkillRecommendationError): ...


class SkillRecommendationProtocol(ABC):
    @abstractmethod
    def recommend(self, request: SkillRecommendationRequest) -> SkillRecommendationResponse:
        """Get recommendation for job.

        Raises:
            SkillRecommendationError - All errors from adapter
            SkillRecommendationNotFound - skills list is empty
        Returns:
            SkillRecommendationResponse: skill for requested job
        """

    ...
