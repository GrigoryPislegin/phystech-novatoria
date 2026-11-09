from dataclasses import dataclass
from typing import Protocol, final

import structlog

from nanimai_platform.domain import (
    CandidateID,
    CriterionAnalysis,
    CriterionID,
    StopFactorAnalysis,
    StopFactorID,
    VacancyID,
)
from nanimai_platform.domain.candidate import Candidate
from nanimai_platform.domain.vacancy import VacancyStageEnum
from nanimai_platform.services.candidate.service import (
    CandidateService,
    CandidateServiceCandidateNotFoundError,
    CandidateServiceError,
    CandidateServiceInvalidDataError,
)
from nanimai_platform.services.criterion.service import CriterionService
from nanimai_platform.services.score_calculation.service import (
    ScoreCalculationService,
    ScoreCalculationServiceCandidateNotFoundError,
    ScoreCalculationServiceError,
    ScoreCalculationServiceVacancyNotFoundError,
)
from nanimai_platform.services.stop_factor.service import StopFactorService
from nanimai_platform.services.vacancy.service import (
    VacancyService,
    VacancyServiceError,
    VacancyServiceInvalidDataError,
    VacancyServiceVacancyNotFoundError,
)
from nanimai_platform.utils.logging_span import span
from nanimai_platform.utils.update_value import UpdateValue

log = structlog.stdlib.get_logger("app.service.CandidateFactorAnalysisCompleteHook")


class CandidateFactorAnalysisCompleteHookError(Exception): ...


class CandidateFactorAnalysisCompleteHookInvalidDataError(Exception): ...


class CandidateFactorAnalysisCompleteHookCandidateNotFoundError(Exception): ...


class CandidateFactorAnalysisCompleteHookVacancyNotFoundError(Exception): ...


class CandidateLike(Protocol):
    id: CandidateID
    vacancy_id: VacancyID
    criteria: dict[CriterionID, CriterionAnalysis]
    stop_factors: dict[StopFactorID, StopFactorAnalysis]


@final
class CandidateFactorAnalysisCompleteHook:
    def __init__(
        self,
        vacancy_service: VacancyService,
        candidate_service: CandidateService,
        score_calculation_service: ScoreCalculationService,
        criteria_service: CriterionService,
        stop_factors_service: StopFactorService,
    ):
        self._vacancy_service = vacancy_service
        self._candidate_service = candidate_service
        self._score_calculation_service = score_calculation_service
        self._criteria_service = criteria_service
        self._stop_factors_service = stop_factors_service

    @dataclass
    class FactorAnalysisCompleteRequest:
        candidate: CandidateLike
        accepted_status: VacancyStageEnum = VacancyStageEnum.SELECTED_AI
        rejected_status: VacancyStageEnum = VacancyStageEnum.REJECTED_AI
        threshold: float | None = None

    @span(op="candidate_factor_analysis_complete_hook", name="factor_analysis_complete")
    async def factor_analysis_complete(self, request: FactorAnalysisCompleteRequest) -> Candidate:
        try:
            criteria = await self._criteria_service.read_many_by_vacancy(
                CriterionService.ReadManyCriteriaByVacancyRequest(vacancy_id=request.candidate.vacancy_id)
            )
            stop_factors = await self._stop_factors_service.read_many_by_vacancy(
                StopFactorService.ReadManyStopFactorsByVacancyRequest(vacancy_id=request.candidate.vacancy_id)
            )

            score = self._score_calculation_service.calculate_score_from_objects(
                ScoreCalculationService.CalculateScoreFromObjectsRequest(
                    criteria=criteria,
                    stop_factors=stop_factors,
                    criteria_analysis=request.candidate.criteria,
                    stop_factors_analysis=request.candidate.stop_factors,
                )
            )

            threshold = request.threshold
            if threshold is None:
                vacancy = await self._vacancy_service.read(
                    VacancyService.ReadVacancyRequest(id=request.candidate.vacancy_id)
                )
                threshold = vacancy.threshold

            if score.score >= threshold:
                candidate = await self._candidate_service.update(
                    CandidateService.UpdateCandidateRequest(
                        id=request.candidate.id,
                        status=UpdateValue(request.accepted_status),
                    )
                )
            else:
                candidate = await self._candidate_service.update(
                    CandidateService.UpdateCandidateRequest(
                        id=request.candidate.id,
                        status=UpdateValue(request.rejected_status),
                    )
                )
            return candidate
        except (VacancyServiceInvalidDataError, CandidateServiceInvalidDataError) as e:
            log.error("Invalid data in factor_analysis_complete_hook", err=e)
            raise CandidateFactorAnalysisCompleteHookInvalidDataError("invalid data") from e
        except (ScoreCalculationServiceCandidateNotFoundError, CandidateServiceCandidateNotFoundError) as e:
            log.error("Candidate not found in factor_analysis_complete_hook", err=e)
            raise CandidateFactorAnalysisCompleteHookCandidateNotFoundError("Candidate not found") from e
        except (ScoreCalculationServiceVacancyNotFoundError, VacancyServiceVacancyNotFoundError) as e:
            log.error("Vacancy not found in factor_analysis_complete_hook", err=e)
            raise CandidateFactorAnalysisCompleteHookVacancyNotFoundError("Vacancy not found") from e
        except (ScoreCalculationServiceError, CandidateServiceError, VacancyServiceError) as e:
            log.error("failed to read/update/score in factor_analysis_complete_hook", err=e)
            raise CandidateFactorAnalysisCompleteHookError("failed to read/update/score") from e
        except Exception as e:
            log.error("Unable to use factor analysis complete", err=e)
            raise CandidateFactorAnalysisCompleteHookError("unknown error") from e
