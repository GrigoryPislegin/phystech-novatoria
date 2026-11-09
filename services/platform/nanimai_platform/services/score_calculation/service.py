from __future__ import annotations

import hashlib
import json
from datetime import timedelta

import structlog
from pydantic import BaseModel, Field

from nanimai_platform.domain.candidate.candidate import CriterionAnalysis, StopFactorAnalysis
from nanimai_platform.domain.criterion import Criterion
from nanimai_platform.domain.scalar.scalars import CandidateID, CriterionID, StopFactorID
from nanimai_platform.domain.stop_factor import StopFactor
from nanimai_platform.services.cache.cache import Cache
from nanimai_platform.services.cache.keyspace import Keyspace
from nanimai_platform.services.candidate.service import CandidateService, CandidateServiceCandidateNotFoundError
from nanimai_platform.services.criterion.service import CriterionService
from nanimai_platform.services.stop_factor.service import StopFactorService
from nanimai_platform.services.vacancy.service import VacancyService, VacancyServiceVacancyNotFoundError

log = structlog.get_logger(__name__)


class ScoreCalculationServiceError(Exception):
    """Base exception for ScoreCalculationService."""


class ScoreCalculationServiceCandidateNotFoundError(ScoreCalculationServiceError):
    """Raised when candidate is not found."""


class ScoreCalculationServiceVacancyNotFoundError(ScoreCalculationServiceError):
    """Raised when vacancy is not found."""


class ScoreCalculationService:
    """Service for calculating candidate scores based on criteria and stop factors."""

    def __init__(
        self,
        candidate_service: CandidateService,
        vacancy_service: VacancyService,
        criterion_service: CriterionService,
        stop_factor_service: StopFactorService,
        cache: Cache,
    ):
        self._candidate_service = candidate_service
        self._vacancy_service = vacancy_service
        self._criterion_service = criterion_service
        self._stop_factor_service = stop_factor_service
        self._cache = cache
        self._ks = Keyspace("score_calculation")
        self._cache_expire = timedelta(hours=24)

    class CalculateCandidateScoreRequest(BaseModel):
        candidate_id: CandidateID = Field(description="Candidate ID to calculate score for")

    class CalculateCandidateScoreResponse(BaseModel):
        score: float = Field(description="Calculated normalized score for the candidate")

    class CalculateScoreFromObjectsRequest(BaseModel):
        criteria: list[Criterion] = Field(description="List of criteria for the vacancy")
        stop_factors: list[StopFactor] = Field(description="List of stop factors for the vacancy")
        criteria_analysis: dict[CriterionID, CriterionAnalysis] = Field(
            default_factory=dict, description="Candidate's criteria analysis results"
        )
        stop_factors_analysis: dict[StopFactorID, StopFactorAnalysis] = Field(
            default_factory=dict, description="Candidate's stop factors analysis results"
        )

    def _generate_cache_key(
        self,
        candidate_id: CandidateID,
        criteria: list[Criterion],
        stop_factors: list[StopFactor],
        criteria_dict: dict[CriterionID, CriterionAnalysis],
        stop_factor_dict: dict[StopFactorID, StopFactorAnalysis],
    ):
        criterion_weights = {c.id: c.initial_weight for c in criteria}
        criteria_analysis = sorted(
            (str(cid), str(criterion_weights[cid]), analysis.status)
            for cid, analysis in criteria_dict.items()
            if cid in criterion_weights
        )

        stop_factor_weights = {sf.id: sf.initial_weight for sf in stop_factors}
        stop_factors_analysis = sorted(
            (str(sid), str(stop_factor_weights[sid]), analysis.status)
            for sid, analysis in stop_factor_dict.items()
            if sid in stop_factor_weights
        )

        stable_key = json.dumps(
            {
                "criteria": criteria_analysis,
                "stop_factors": stop_factors_analysis,
            },
            sort_keys=True,
        )
        criteria_hash = hashlib.sha256(stable_key.encode()).hexdigest()
        return self._ks.key(str(candidate_id), criteria_hash)

    async def calculate_candidate_score(  # noqa: C901
        self, request: CalculateCandidateScoreRequest
    ) -> CalculateCandidateScoreResponse:
        """
        Calculate the candidate score based on the vacancy criteria and stop factors.

        The calculation follows these steps:
        1. Calculate the total weight of all criteria
        2. Calculate the initial score by summing weighted criterion scores
        3. Normalize the score by dividing by total weight
        4. Apply penalties for any active stop factors

        Returns the normalized score between 0 and 1.
        """
        try:
            candidate = await self._candidate_service.read(
                CandidateService.ReadCandidateRequest(id=request.candidate_id)
            )

            criteria = await self._criterion_service.read_many_by_vacancy(
                CriterionService.ReadManyCriteriaByVacancyRequest(vacancy_id=candidate.vacancy_id)
            )

            stop_factors = await self._stop_factor_service.read_many_by_vacancy(
                StopFactorService.ReadManyStopFactorsByVacancyRequest(vacancy_id=candidate.vacancy_id)
            )

            cache_key = self._generate_cache_key(
                candidate_id=request.candidate_id,
                criteria=criteria,
                stop_factors=stop_factors,
                criteria_dict=candidate.criteria or {},
                stop_factor_dict=candidate.stop_factors or {},
            )

            cached_response = await self._cache.get(cache_key, t=self.CalculateCandidateScoreResponse)
            if cached_response is not None:
                log.info(
                    "Returning cached score calculation result",
                    candidate_id=request.candidate_id,
                    score=cached_response.score,
                )
                return cached_response

            response = self.calculate_score_from_objects(
                self.CalculateScoreFromObjectsRequest(
                    criteria=criteria,
                    stop_factors=stop_factors,
                    criteria_analysis=candidate.criteria or {},
                    stop_factors_analysis=candidate.stop_factors or {},
                )
            )

            await self._cache.set(cache_key, response, expire=self._cache_expire)

            log.info("Score calculated and cached", candidate_id=request.candidate_id, score=response.score)

            return response

        except CandidateServiceCandidateNotFoundError as e:
            log.error("Failed to find candidate", err=e, candidate_id=request.candidate_id)
            raise ScoreCalculationServiceCandidateNotFoundError("Candidate not found") from e
        except VacancyServiceVacancyNotFoundError as e:
            log.error("Failed to find vacancy", err=e, candidate_id=request.candidate_id)
            raise ScoreCalculationServiceVacancyNotFoundError("Vacancy not found") from e
        except Exception as e:
            log.error(
                "Failed to calculate candidate score",
                err=e,
                candidate_id=request.candidate_id,
            )
            raise ScoreCalculationServiceError("Failed to calculate score") from e

    def calculate_score_from_objects(
        self, request: CalculateScoreFromObjectsRequest
    ) -> CalculateCandidateScoreResponse:
        criteria = request.criteria
        stop_factors = request.stop_factors
        criteria_analysis = request.criteria_analysis
        stop_factors_analysis = request.stop_factors_analysis

        total_weight = sum(criterion.initial_weight for criterion in criteria)

        if total_weight == 0:
            return self.CalculateCandidateScoreResponse(score=0.0)

        score = 0.0

        for criterion in criteria:
            candidate_criterion = criteria_analysis.get(criterion.id)
            if candidate_criterion and candidate_criterion.score is not None:
                score += candidate_criterion.score * criterion.initial_weight

        normalized_score = score / total_weight

        for stop_factor in stop_factors:
            candidate_stop_factor = stop_factors_analysis.get(stop_factor.id)
            if candidate_stop_factor and candidate_stop_factor.status:
                normalized_score -= stop_factor.initial_weight / 100

        normalized_score = max(0.0, normalized_score)

        return self.CalculateCandidateScoreResponse(score=normalized_score)
