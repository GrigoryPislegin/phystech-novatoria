from __future__ import annotations

import asyncio
from typing import final

import structlog
from pydantic import BaseModel, Field

from nanimai_platform.domain.candidate.candidate import Candidate, CandidateAnalysisStatusEnum
from nanimai_platform.domain.scalar.scalars import VacancyID
from nanimai_platform.domain.vacancy.vacancy import VacancyStageEnum
from nanimai_platform.services.candidate.factor_analysis_complete_hook import (
    CandidateFactorAnalysisCompleteHook,
    CandidateFactorAnalysisCompleteHookCandidateNotFoundError,
    CandidateFactorAnalysisCompleteHookError,
    CandidateFactorAnalysisCompleteHookInvalidDataError,
    CandidateFactorAnalysisCompleteHookVacancyNotFoundError,
)
from nanimai_platform.services.candidate.service import CandidateService
from nanimai_platform.services.score_calculation.service import ScoreCalculationService
from nanimai_platform.services.vacancy.service import VacancyService
from nanimai_platform.utils.logging_span import span

log = structlog.stdlib.get_logger("app.service.RebalanceVacancyCandidatesHook")


class RebalanceVacancyCandidatesHookError(Exception): ...


class RebalanceVacancyCandidatesHookInvalidDataError(Exception): ...


class RebalanceVacancyCandidatesHookCandidateNotFoundError(Exception): ...


class RebalanceVacancyCandidatesHookVacancyNotFoundError(Exception): ...


@final
class RebalanceVacancyCandidatesHook:
    def __init__(
        self,
        vacancy_service: VacancyService,
        candidate_service: CandidateService,
        score_calculation_service: ScoreCalculationService,
        factor_analysis_hook: CandidateFactorAnalysisCompleteHook,
    ):
        self._vacancy_service = vacancy_service
        self._candidate_service = candidate_service
        self._score_calculation_service = score_calculation_service
        self._factor_analysis_hook = factor_analysis_hook

    class RebalanceVacancyCandidates(BaseModel):
        vacancy_id: VacancyID
        new_threshold: float = Field(ge=0, le=1)
        accepted_status: VacancyStageEnum = VacancyStageEnum.SELECTED_AI
        rejected_status: VacancyStageEnum = VacancyStageEnum.REJECTED_AI

    @span(op="rebalance_vacancy_candidates_hook", name="rebalance_vacancy_candidates")
    async def rebalance_vacancy_candidates(self, request: RebalanceVacancyCandidates) -> list[Candidate]:
        try:
            candidates = await self._candidate_service.read_many_candidate_cards(
                CandidateService.ReadManyCandidateCardsRequest(vacancy_id=request.vacancy_id)
            )

            candidates = filter(
                lambda x: (
                    x.status
                    in [
                        VacancyStageEnum.MAGIC_AI,
                        request.accepted_status,
                        request.rejected_status,
                    ]
                    and x.analysis_status
                    in [
                        CandidateAnalysisStatusEnum.SUCCESS,
                        CandidateAnalysisStatusEnum.FAILED,
                    ]
                ),
                candidates,
            )

            return await asyncio.gather(*[  # todo: оптимизировать загрузку, на каждого кандидата грузим критерии из бд
                self._factor_analysis_hook.factor_analysis_complete(
                    self._factor_analysis_hook.FactorAnalysisCompleteRequest(
                        candidate=candidate,
                        accepted_status=request.accepted_status,
                        rejected_status=request.rejected_status,
                        threshold=request.new_threshold,
                    )
                )
                for candidate in candidates
            ])
        except CandidateFactorAnalysisCompleteHookInvalidDataError as e:
            log.error("Invalid data in rebalance_vacancy_candidates_hook", err=e)
            raise RebalanceVacancyCandidatesHookInvalidDataError("invalid data") from e
        except CandidateFactorAnalysisCompleteHookCandidateNotFoundError as e:
            log.error("Candidate not found in rebalance_vacancy_candidates_hook", err=e)
            raise RebalanceVacancyCandidatesHookCandidateNotFoundError("Candidate not found") from e
        except CandidateFactorAnalysisCompleteHookVacancyNotFoundError as e:
            log.error("Vacancy not found in rebalance_vacancy_candidates_hook", err=e)
            raise RebalanceVacancyCandidatesHookVacancyNotFoundError("Vacancy not found") from e
        except CandidateFactorAnalysisCompleteHookError as e:
            log.error("Unable to use factor_analysis_complete_hook", err=e)
            raise RebalanceVacancyCandidatesHookError("factor_analysis_complete_hook error") from e
        except Exception as e:
            log.error("failed to rebalance_vacancy_candidates", err=e)
            raise RebalanceVacancyCandidatesHookError("unknown error") from e
