from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from statistics import mean, median
from typing import final
from uuid import uuid4

import structlog
from dateutil.relativedelta import relativedelta
from pydantic import BaseModel
from pydantic_extra_types.currency_code import ISO4217 as CurrencyISO4217

from nanimai_platform.domain.candidate.candidate import (
    CandidateAnalysisStatusEnum,
    CandidateCard,
    CandidateSourceEnum,
    CriterionStatusEnum,
)
from nanimai_platform.domain.criterion.criterion import Criterion
from nanimai_platform.domain.project.project import Project, ProjectStatistics
from nanimai_platform.domain.scalar.scalars import CriterionID, ProjectID, StopFactorID, UserID, VacancyID
from nanimai_platform.domain.statistics.statistics import (
    CandidateCriterionStatus,
    CandidateCriterionStopFactorStatusStatistics,
    CandidateDateIncreaseStatistics,
    CandidateSalaryStatistics,
    CandidateScoreStatistics,
    CandidateStageStatistics,
    CandidateStopFactorStatus,
    Statistics,
    VacancyCandidatesStatistics,
)
from nanimai_platform.domain.stop_factor.stop_factor import StopFactor
from nanimai_platform.domain.vacancy.vacancy import Vacancy, VacancyStageEnum, VacancyStatistics, VacancyStatus
from nanimai_platform.protocols.internal import repository as protocol
from nanimai_platform.protocols.internal.repository import (
    CandidateRepositoryProtocol,
    CriterionRepositoryProtocol,
    ProjectRepositoryProtocol,
    StatisticsRepositoryProtocol,
    StopFactorRepositoryProtocol,
    VacancyRepositoryProtocol,
)
from nanimai_platform.services.cache.cache import Cache
from nanimai_platform.services.cache.keyspace import Key, Keyspace
from nanimai_platform.services.project.service import ProjectService, ProjectServiceProjectNotFoundError
from nanimai_platform.services.score_calculation.service import ScoreCalculationService
from nanimai_platform.services.user_profile.service import UserService
from nanimai_platform.services.vacancy import (
    VacancyServiceError,
    VacancyServiceInvalidDataError,
    VacancyServiceVacancyNotFoundError,
)
from nanimai_platform.utils import UpdateValue
from nanimai_platform.utils.asyncio_background import launch_background
from nanimai_platform.utils.logging_span import span

log = structlog.stdlib.get_logger("app.service.StatisticsService")


class StatisticsServiceError(Exception): ...


class StatisticsServiceInvalidDataError(Exception): ...


class StatisticsServiceStatisticsNotFoundError(Exception): ...


class StatisticsServiceVacancyNotFoundError(Exception): ...


class StatisticsServiceProjectNotFoundError(Exception): ...


class StatisticsServiceCalculationError(Exception): ...


@final
class StatisticsService:
    def __init__(
        self,
        cache: Cache,
        statistics_repo: StatisticsRepositoryProtocol,
        vacancy_repo: VacancyRepositoryProtocol,
        candidate_repo: CandidateRepositoryProtocol,
        project_service: ProjectService,
        project_repo: ProjectRepositoryProtocol,
        score_calculation_service: ScoreCalculationService,
        criterion_repo: CriterionRepositoryProtocol,
        stop_factor_repo: StopFactorRepositoryProtocol,
        user_service: UserService,
    ):
        self._cache = cache
        self._ks = Keyspace("statistics_service")
        self._statistics_repo = statistics_repo
        self._vacancy_repo = vacancy_repo
        self._project_service = project_service
        self._project_repo = project_repo
        self._candidate_repo = candidate_repo
        self._score_calculation_service = score_calculation_service
        self._criterion_repo = criterion_repo
        self._stop_factor_repo = stop_factor_repo
        self._user_service = user_service
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._sleep_between_updates_sec = 600
        self.trace_id = uuid4().hex

    class ReadStatisticsByVacancyRequest(BaseModel):
        vacancy_id: VacancyID

    @span(op="statistics_service", name="read_statistics_by_vacancy")
    async def read_by_vacancy(self, request: ReadStatisticsByVacancyRequest) -> Statistics:
        try:
            if (
                statistics := await self._cache.get(self._statistics_by_vacancy_key(request.vacancy_id), t=Statistics)
            ) is not None:
                return statistics

            statistics = await self._statistics_repo.read_statistics_by_vacancy(
                StatisticsRepositoryProtocol.ReadStatisticsByVacancyRequest(vacancy_id=request.vacancy_id)
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._statistics_by_vacancy_key(statistics.vacancy_id), statistics)
                await self._cache.sadd(
                    self._project_set_by_vacancy_key(statistics.project_id), {"vacancy_id": str(statistics.vacancy_id)}
                )

            update_cache()

            return statistics

        except protocol.StatisticsNotFoundError as e:
            log.error("failed to find statistics", err=e)
            raise StatisticsServiceStatisticsNotFoundError("statistics not found") from e
        except protocol.StatisticsValidateError as e:
            log.error("failed to read statistics due to validation error", err=e)
            raise StatisticsServiceInvalidDataError("invalid data") from e
        except protocol.ReadStatisticsError as e:
            log.error("failed to read statistics", err=e)
            raise StatisticsServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read statistics", err=e)
            raise StatisticsServiceError("unknown error") from e

    class UpdateStatisticsByVacancyRequest(BaseModel):
        vacancy_id: VacancyID

        project_statistics: ProjectStatistics | None = None
        vacancy_statistics: VacancyCandidatesStatistics | None = None
        score_statistics: CandidateScoreStatistics | None = None
        stage_statistics: CandidateStageStatistics | None = None
        criterion_stop_factor_status_statistics: CandidateCriterionStopFactorStatusStatistics | None = None
        date_increase_statistics: CandidateDateIncreaseStatistics | None = None
        salary_statistics: CandidateSalaryStatistics | None = None

    @span(op="statistics_service", name="upsert_statistics_by_vacancy")
    async def upsert_by_vacancy(self, request: UpdateStatisticsByVacancyRequest) -> Statistics:
        try:
            statistics = await self._statistics_repo.update_or_create_statistics_by_vacancy(
                StatisticsRepositoryProtocol.UpdateStatisticsByVacancyRequest(
                    vacancy_id=request.vacancy_id,
                    project_statistics=request.project_statistics,
                    vacancy_statistics=request.vacancy_statistics,
                    score_statistics=request.score_statistics,
                    stage_statistics=request.stage_statistics,
                    criterion_stop_factor_status_statistics=request.criterion_stop_factor_status_statistics,
                    date_increase_statistics=request.date_increase_statistics,
                    salary_statistics=request.salary_statistics,
                )
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._statistics_by_vacancy_key(statistics.vacancy_id), statistics)
                await self._cache.sadd(
                    self._project_set_by_vacancy_key(statistics.project_id), {"vacancy_id": str(statistics.vacancy_id)}
                )

            update_cache()

            return statistics

        except protocol.VacancyNotFoundError as e:
            log.error("failed to create statistics due to vacancy not found", err=e)
            raise StatisticsServiceVacancyNotFoundError("vacancy not found") from e
        except protocol.StatisticsValidateError as e:
            log.error("failed to update statistics due to validation error", err=e)
            raise StatisticsServiceInvalidDataError("invalid data") from e
        except protocol.CreateStatisticsError as e:
            log.error("failed to create statistics", err=e)
            raise StatisticsServiceError("failed to create") from e
        except protocol.UpdateStatisticsError as e:
            log.error("failed to update statistics", err=e)
            raise StatisticsServiceError("failed to update") from e
        except protocol.StatisticsWithVacancyAlreadyExistsError as e:
            log.error("failed to create statistics due to already existing", err=e)
            raise StatisticsServiceError("failed to create") from e
        except Exception as e:
            log.error("failed to update statistics", err=e)
            raise StatisticsServiceError("unknown error") from e

    class ReadManyStatisticsByProjectRequest(BaseModel):
        project_id: ProjectID

    @span(op="statistics_service", name="read_many_statistics_by_project")
    async def read_many_by_project(self, request: ReadManyStatisticsByProjectRequest) -> list[Statistics]:  # noqa: C901
        try:
            many_statistics: dict[VacancyID, Statistics] = {}

            _ = await self._project_service.read(self._project_service.ReadProjectRequest(id=request.project_id))

            statistics_set: list[str] = [
                d["vacancy_id"]
                for d in (await self._cache.smembers(self._project_set_by_vacancy_key(request.project_id)))
            ]
            log.info("retrieved statistics set from cache", count=len(statistics_set))

            if not statistics_set:
                db_only_statistics = await self._statistics_repo.read_many_statistics_by_project(
                    StatisticsRepositoryProtocol.ReadManyStatisticsByProjectRequest(project_id=request.project_id)
                )
                log.info("retrieved statistics from db", count=len(db_only_statistics))

                @launch_background
                async def update_cache():
                    log.info("invalidating project set cache for statistics", project_id=request.project_id)
                    await self._cache.invalidate(self._project_set_by_vacancy_key(request.project_id))

                    if db_only_statistics:
                        await self._cache.mset({
                            self._statistics_by_vacancy_key(one_statistics.vacancy_id): one_statistics
                            for one_statistics in db_only_statistics
                        })
                        await self._cache.sadd(
                            self._project_set_by_vacancy_key(request.project_id),
                            *[{"vacancy_id": str(one_statistics.vacancy_id)} for one_statistics in db_only_statistics],
                        )

                update_cache()

                return db_only_statistics

            cache_statistics = await self._cache.mget(
                [self._statistics_by_vacancy_key(VacancyID(vacancy_id)) for vacancy_id in statistics_set], t=Statistics
            )
            log.info("retrieved statistics entities from cache", count=len(cache_statistics))

            from_cache = 0
            for one_statistics_cache in cache_statistics:
                if one_statistics_cache is not None:
                    many_statistics[one_statistics_cache.vacancy_id] = one_statistics_cache
                    from_cache += 1

            retrieve_from_db = list(
                {VacancyID(vacancy_id) for vacancy_id in statistics_set} - set(many_statistics.keys())
            )
            db_statistics = await self._statistics_repo.read_many_statistics_by_vacancies(
                StatisticsRepositoryProtocol.ReadManyStatisticsByVacanciesRequest(vacancy_ids=retrieve_from_db)
            )
            log.info("retrieved statistics from db", count=len(db_statistics))
            from_db = 0
            for one_statistics_db in db_statistics:
                if one_statistics_db is not None:
                    many_statistics[one_statistics_db.vacancy_id] = one_statistics_db
                    from_db += 1

            log.info(
                "cache hit: statistics retrieved",
                count=len(many_statistics),
                cache_hit_ratio=from_cache / len(many_statistics),
                db_hit_ratio=from_db / len(many_statistics),
            )

            @launch_background
            async def update_cache():
                log.info("invalidating project set cache for statistics", project_id=request.project_id)
                await self._cache.invalidate(self._project_set_by_vacancy_key(request.project_id))

                if many_statistics:
                    await self._cache.mset({
                        self._statistics_by_vacancy_key(one_statistics.vacancy_id): one_statistics
                        for one_statistics in many_statistics.values()
                    })
                    await self._cache.sadd(
                        self._project_set_by_vacancy_key(request.project_id),
                        *[
                            {"vacancy_id": str(one_statistics.vacancy_id)}
                            for one_statistics in many_statistics.values()
                        ],
                    )

                update_cache()

            return list(many_statistics.values())
        except ProjectServiceProjectNotFoundError as e:
            log.error("failed to find project", err=e)
            raise StatisticsServiceProjectNotFoundError("project not found") from e
        except protocol.StatisticsValidateError as e:
            log.error("failed to read many statistics due to validation error", err=e)
            raise StatisticsServiceInvalidDataError("invalid data") from e
        except protocol.ReadStatisticsError as e:
            log.error("failed to read many statistics by project", err=e)
            raise StatisticsServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read many statistics by project", err=e)
            raise StatisticsServiceError("unknown error") from e

    class CalculateProjectStatisticsRequest(BaseModel):
        candidates_by_project: list[CandidateCard]
        vacancies_by_project: list[Vacancy]

    @span(op="statistics_service", name="calculate_project_statistics")
    def calculate_project_statistics(self, request: CalculateProjectStatisticsRequest) -> ProjectStatistics:
        try:
            candidates = request.candidates_by_project
            vacancies = request.vacancies_by_project

            return ProjectStatistics(
                total_candidates=len(candidates),
                total_vacancies=len(vacancies),
                active_vacancies=sum(1 if vacancy.status == VacancyStatus.OPEN else 0 for vacancy in vacancies),
            )

        except Exception as e:
            log.error("failed to calculate project statistics", err=e)
            raise StatisticsServiceCalculationError("calculate project statistics error") from e

    class CalculateVacancyStatisticsRequest(BaseModel):
        candidates_by_vacancy: list[CandidateCard]

    @span(op="candidate_service", name="calculate_vacancy_statistics")
    def calculate_vacancy_statistics(self, request: CalculateVacancyStatisticsRequest) -> VacancyCandidatesStatistics:
        # todo: можно ускорить тем, что будем считать только сегодняшнюю статистику и ее приплюсовывать,
        #  а не считать всех (работает при условии что наш сервер работает каждый день, иначе еще что-то придумать)
        try:
            stats = VacancyCandidatesStatistics(
                total_candidates=0,
                total_today_increase=0,
                platform_candidates=0,
                platform_today_increase=0,
                hh_candidates=0,
                hh_today_increase=0,
                total_dirty_candidates=0,
                dirty_today_increase=0,
            )

            candidates = request.candidates_by_vacancy

            today = datetime.now(UTC).date()

            stats.total_candidates = len(candidates)
            stats.total_dirty_candidates = sum(1 if candidate.dirty else 0 for candidate in candidates)
            for candidate in candidates:
                is_platform = candidate.source in {CandidateSourceEnum.NANIMAI, CandidateSourceEnum.NANIMAI_JOBBOARD}
                is_headhunter = candidate.source in {CandidateSourceEnum.HH, CandidateSourceEnum.HH_SEARCH_CAMPAIGN}

                if is_platform:
                    stats.platform_candidates += 1

                if is_headhunter:
                    stats.hh_candidates += 1

                if candidate.created_at.date() != today:
                    continue

                stats.total_today_increase += 1

                if candidate.dirty:
                    stats.dirty_today_increase += 1

                if is_platform:
                    stats.platform_today_increase += 1

                if is_headhunter:
                    stats.hh_today_increase += 1

            return stats
        except Exception as e:
            log.error("failed to calculate vacancy statistics", err=e)
            raise StatisticsServiceCalculationError("calculate vacancy statistics error") from e

    class CalculateScoreStatisticsRequest(BaseModel):
        candidate_scores: list[float]

    @span(op="statistics_service", name="calculate_score_statistics")
    def calculate_score_statistics(self, request: CalculateScoreStatisticsRequest) -> CandidateScoreStatistics:
        try:
            buckets = list(range(0, 105, 5))
            response = CandidateScoreStatistics(
                statistics={bucket: 0 for bucket in buckets},
            )

            for candidate_score in request.candidate_scores:
                score = int((candidate_score * 100) // 1)
                if score < 0 or score > 100:
                    raise ValueError("invalid score")

                response.statistics[score // 5 * 5] += 1

            return response

        except Exception as e:
            log.error("failed to calculate score statistics", err=e)
            raise StatisticsServiceCalculationError("calculate score statistics error") from e

    class CalculateStageStatisticsRequest(BaseModel):
        candidates_by_vacancy: list[CandidateCard]

    @span(op="statistics_service", name="calculate_stage_statistics")
    def calculate_stage_statistics(self, request: CalculateStageStatisticsRequest) -> CandidateStageStatistics:
        try:
            candidates = request.candidates_by_vacancy

            stages = list(VacancyStageEnum)
            statistics = {stage: 0 for stage in stages}

            for candidate in candidates:
                for stage in candidate.status_history:
                    statistics[stage] += 1

            return CandidateStageStatistics(
                statistics=statistics,
            )

        except Exception as e:
            log.error("failed to calculate stage statistics", err=e)
            raise StatisticsServiceCalculationError("calculate stage statistics error") from e

    class CalculateCriterionStopFactorStatusStatisticsRequest(BaseModel):
        candidates_by_vacancy: list[CandidateCard]
        criteria_by_vacancy: list[Criterion]
        stop_factors_by_vacancy: list[StopFactor]

    @span(op="statistics_service", name="calculate_criterion_stop_factor_status_statistics")
    def calculate_criterion_stop_factor_status_statistics(
        self, request: CalculateCriterionStopFactorStatusStatisticsRequest
    ) -> CandidateCriterionStopFactorStatusStatistics:
        try:
            candidates = request.candidates_by_vacancy
            vacancy_criteria = request.criteria_by_vacancy
            vacancy_stop_factors = request.stop_factors_by_vacancy

            criterion_statuses = list(CriterionStatusEnum)
            criterion_status_statistics_unfilled = CandidateCriterionStatus(
                statistics={cr_s: 0 for cr_s in criterion_statuses}
            )

            criterion_status_statistics: dict[CriterionID, CandidateCriterionStatus] = {
                criterion.id: criterion_status_statistics_unfilled.model_copy(deep=True)
                for criterion in vacancy_criteria
            }

            stop_factor_statuses = [True, False]
            stop_factor_status_statistics_unfilled = CandidateStopFactorStatus(
                statistics={sf_s: 0 for sf_s in stop_factor_statuses}
            )

            stop_factor_status_statistics: dict[StopFactorID, CandidateStopFactorStatus] = {
                stop_factor.id: stop_factor_status_statistics_unfilled.model_copy(deep=True)
                for stop_factor in vacancy_stop_factors
            }

            for candidate in candidates:
                for candidate_cr_id, candidate_cr_analysis in candidate.criteria.items():
                    if candidate_cr_id in criterion_status_statistics and candidate_cr_analysis.status is not None:
                        criterion_status_statistics[candidate_cr_id].statistics[candidate_cr_analysis.status] += 1

                for candidate_sf_id, candidate_sf_analysis in candidate.stop_factors.items():
                    if candidate_sf_id in stop_factor_status_statistics and candidate_sf_analysis.status is not None:
                        stop_factor_status_statistics[candidate_sf_id].statistics[candidate_sf_analysis.status] += 1

            return CandidateCriterionStopFactorStatusStatistics(
                criterion_status_statistics=criterion_status_statistics,
                stop_factor_status_statistics=stop_factor_status_statistics,
            )

        except Exception as e:
            log.error("failed to calculate criterion and stop factor status statistics", err=e)
            raise StatisticsServiceCalculationError(
                "calculate criterion and stop factor status statistics error"
            ) from e

    class CalculateCandidateDateIncreaseStatisticsRequest(BaseModel):
        candidates_by_vacancy: list[CandidateCard]

    @span(op="statistics_service", name="calculate_candidate_date_increase_statistics")
    def calculate_candidate_date_increase_statistics(
        self, request: CalculateCandidateDateIncreaseStatisticsRequest
    ) -> CandidateDateIncreaseStatistics:
        # todo: мб стоит пересчитывать не все 3 месяца а только последний день и дни между последним анализом и сегодняшним
        #  в идеале это максимум 1 день
        try:
            candidates = request.candidates_by_vacancy

            today = datetime.now(UTC).date()
            start_day = today - relativedelta(months=3)

            response = CandidateDateIncreaseStatistics(statistics={})
            current = start_day
            while current <= today:
                response.statistics[current] = {source: 0 for source in CandidateSourceEnum}
                current += timedelta(days=1)

            for candidate in candidates:
                created_date = candidate.created_at.date()

                if created_date < start_day or created_date > today:
                    continue

                response.statistics[created_date][candidate.source] += 1

            return response
        except Exception as e:
            log.error("failed to calculate candidate date increase statistics", err=e)
            raise StatisticsServiceCalculationError("calculate candidate date increase statistics error") from e

    class CalculateCandidateSalaryStatisticsRequest(BaseModel):
        candidates_by_vacancy: list[CandidateCard]

    @span(op="statistics_service", name="calculate_salary_statistics")
    def calculate_salary_statistics(
        self, request: CalculateCandidateSalaryStatisticsRequest
    ) -> CandidateSalaryStatistics:
        try:
            salary_list: list[int] = []

            for candidate in request.candidates_by_vacancy:
                salary = candidate.expected_salary
                if salary is None or salary.currency != CurrencyISO4217("RUB") or salary.value == 0:
                    continue
                salary_list.append(salary.value)

            if not salary_list or len(salary_list) == 0:
                return CandidateSalaryStatistics(currency=CurrencyISO4217("RUB"), count=0, average=0, median=0)

            return CandidateSalaryStatistics(
                currency=CurrencyISO4217("RUB"),
                count=len(salary_list),
                average=mean(salary_list),
                median=median(salary_list),
            )
        except Exception as e:
            log.error("failed to calculate candidate salary statistics", err=e)
            raise StatisticsServiceCalculationError("calculate candidate salary statistics error") from e

    class CalculateAndUpdateStatisticsByVacancyRequest(BaseModel):
        vacancy_id: VacancyID
        candidates_by_vacancy: list[CandidateCard]
        candidates_scores: list[float]
        criteria_by_vacancy: list[Criterion]
        stop_factors_by_vacancy: list[StopFactor]
        project_statistics: ProjectStatistics | None = None

    @span(op="statistics_service", name="calculate_and_update_statistics_by_vacancy")
    async def calculate_and_update_statistics_by_vacancy(
        self, request: CalculateAndUpdateStatisticsByVacancyRequest
    ) -> Statistics:
        try:
            vacancy_statistics = self.calculate_vacancy_statistics(
                self.CalculateVacancyStatisticsRequest(candidates_by_vacancy=request.candidates_by_vacancy)
            )

            _ = await self._vacancy_repo.update_vacancy(
                self._vacancy_repo.UpdateVacancyRequest(
                    id=request.vacancy_id,
                    statistics=UpdateValue(
                        value=VacancyStatistics(
                            total_candidates=vacancy_statistics.total_candidates,
                            platform_candidates=vacancy_statistics.platform_candidates,
                            delegated_candidates=vacancy_statistics.hh_candidates,
                        ),
                    ),
                )
            )

            score_statistics = self.calculate_score_statistics(
                self.CalculateScoreStatisticsRequest(candidate_scores=request.candidates_scores)
            )
            stage_statistics = self.calculate_stage_statistics(
                self.CalculateStageStatisticsRequest(candidates_by_vacancy=request.candidates_by_vacancy)
            )
            criterion_stop_factor_status_statistics = self.calculate_criterion_stop_factor_status_statistics(
                self.CalculateCriterionStopFactorStatusStatisticsRequest(
                    candidates_by_vacancy=request.candidates_by_vacancy,
                    criteria_by_vacancy=request.criteria_by_vacancy,
                    stop_factors_by_vacancy=request.stop_factors_by_vacancy,
                )
            )
            date_increase_statistics = self.calculate_candidate_date_increase_statistics(
                self.CalculateCandidateDateIncreaseStatisticsRequest(
                    candidates_by_vacancy=request.candidates_by_vacancy,
                )
            )
            salary_statistics = self.calculate_salary_statistics(
                self.CalculateCandidateSalaryStatisticsRequest(
                    candidates_by_vacancy=request.candidates_by_vacancy,
                )
            )
            statistics = await self.upsert_by_vacancy(
                self.UpdateStatisticsByVacancyRequest(
                    vacancy_id=request.vacancy_id,
                    project_statistics=request.project_statistics,
                    vacancy_statistics=vacancy_statistics,
                    score_statistics=score_statistics,
                    stage_statistics=stage_statistics,
                    criterion_stop_factor_status_statistics=criterion_stop_factor_status_statistics,
                    date_increase_statistics=date_increase_statistics,
                    salary_statistics=salary_statistics,
                )
            )

            return statistics
        except VacancyServiceInvalidDataError as e:
            log.error("failed to update vacancy due to validation error", err=e)
            raise StatisticsServiceInvalidDataError("invalid data") from e
        except VacancyServiceVacancyNotFoundError as e:
            log.error("failed to find vacancy", err=e)
            raise StatisticsServiceVacancyNotFoundError("failed to find") from e
        except VacancyServiceError as e:
            log.error("failed to update vacancy", err=e)
            raise StatisticsServiceError("failed to update") from e

        except StatisticsServiceCalculationError as e:
            log.error("failed to calculate statistics", err=e)
            raise e
        except (StatisticsServiceVacancyNotFoundError, StatisticsServiceInvalidDataError, StatisticsServiceError) as e:
            log.error("failed to update statistics", err=e)
            raise e
        except Exception as e:
            log.error("failed to calculate and update statistics", err=e)
            raise StatisticsServiceError("unknown error") from e

    class ReadManyCandidateCardsRequest(BaseModel):
        vacancy_id: VacancyID

    @span(op="statistics_service", name="read_many_candidate_cards")
    async def _read_many_candidate_cards(self, request: ReadManyCandidateCardsRequest) -> list[CandidateCard]:  # noqa: C901
        try:
            cards = await self._candidate_repo.read_many_candidate_cards(
                CandidateRepositoryProtocol.ReadManyCandidateCards(
                    vacancy_id=request.vacancy_id,
                )
            )
            return cards
        except protocol.CandidateValidateError as e:
            log.error("failed to read many candidates by vacancy due to validation error", err=e)
            raise StatisticsServiceInvalidDataError("invalid data") from e
        except protocol.ReadCandidateError as e:
            log.error("failed to read many candidates by vacancy", err=e)
            raise StatisticsServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read many candidates by vacancy", err=e)
            raise StatisticsServiceError("unknown error") from e

    class ReadManyCriteriaByVacancyRequest(BaseModel):
        vacancy_id: VacancyID

    @span(op="statistics_service", name="read_many_criteria_by_vacancy")
    async def _read_many_criteria_by_vacancy(self, request: ReadManyCriteriaByVacancyRequest) -> list[Criterion]:  # noqa: C901
        try:
            criteria = await self._criterion_repo.read_many_criteria_by_vacancy(
                CriterionRepositoryProtocol.ReadManyCriteriaByVacancyRequest(vacancy_id=request.vacancy_id)
            )
            return criteria
        except protocol.CriterionValidateError as e:
            log.error("failed to read many criteria due to validation error", err=e)
            raise StatisticsServiceInvalidDataError("invalid data") from e
        except protocol.ReadCriterionError as e:
            log.error("failed to read many criteria by vacancy", err=e)
            raise StatisticsServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read many criteria by vacancy", err=e)
            raise StatisticsServiceError("unknown error") from e

    class ReadManyStopFactorsByVacancyRequest(BaseModel):
        vacancy_id: VacancyID

    @span(op="statistics_service", name="read_many_stop_factors_by_vacancy")
    async def _read_many_stop_factors_by_vacancy(
        self, request: ReadManyStopFactorsByVacancyRequest
    ) -> list[StopFactor]:  # noqa: C901
        try:
            stop_factors = await self._stop_factor_repo.read_many_stop_factors_by_vacancy(
                StopFactorRepositoryProtocol.ReadManyStopFactorsByVacancyRequest(vacancy_id=request.vacancy_id)
            )
            return stop_factors
        except protocol.StopFactorValidateError as e:
            log.error("failed to read many stop factors due to validation error", err=e)
            raise StatisticsServiceInvalidDataError("invalid data") from e
        except protocol.ReadStopFactorError as e:
            log.error("failed to read many stop factors by vacancy", err=e)
            raise StatisticsServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read many stop factors by vacancy", err=e)
            raise StatisticsServiceError("unknown error") from e

    class ReadManyProjectsByUserRequest(BaseModel):
        user_id: UserID

    @span(op="project_service", name="read_many_projects_by_user")
    async def _read_many_projects_by_user(self, request: ReadManyProjectsByUserRequest) -> list[Project]:  # noqa: C901
        try:
            projects = await self._project_repo.read_many_projects_by_user(
                ProjectRepositoryProtocol.ReadManyProjectsByUserRequest(user_id=request.user_id)
            )
            return projects
        except protocol.ProjectValidateError as e:
            log.error("failed to read many projects by user due to validation error", err=e)
            raise StatisticsServiceInvalidDataError from e
        except protocol.ReadProjectError as e:
            log.error("failed to read many projects by user", err=e)
            raise StatisticsServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read many stop projects by user", err=e)
            raise StatisticsServiceError("unknown error") from e

    class ReadManyVacanciesByProjectRequest(BaseModel):
        project_id: ProjectID

    @span(op="vacancy_service", name="read_many_by_project")
    async def _read_many_vacancies_by_project(self, request: ReadManyVacanciesByProjectRequest) -> list[Vacancy]:  # noqa: C901
        try:
            vacancies = await self._vacancy_repo.read_many_vacancies_by_project(
                VacancyRepositoryProtocol.ReadManyVacanciesByProjectRequest(project_id=request.project_id)
            )
            return vacancies
        except protocol.VacancyValidateError as e:
            log.error("failed to read many vacancies by project due to validation error", err=e)
            raise StatisticsServiceInvalidDataError("invalid data") from e
        except protocol.ReadVacancyError as e:
            log.error("failed to read many vacancies by project", err=e)
            raise StatisticsServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read many vacancies by project", err=e)
            raise StatisticsServiceError("unknown error") from e

    class CalculateAndUpdateManyStatisticsByProjectRequest(BaseModel):
        project_id: ProjectID

    @span(op="statistics_service", name="calculate_and_update_many_statistics_by_project")
    async def calculate_and_update_many_statistics_by_project(
        self, request: CalculateAndUpdateManyStatisticsByProjectRequest
    ) -> None:
        try:
            vacancies_by_project = await self._read_many_vacancies_by_project(
                self.ReadManyVacanciesByProjectRequest(project_id=request.project_id)
            )

            candidates_by_project: list[CandidateCard] = []
            candidates_by_vacancies: dict[VacancyID, list[CandidateCard]] = {}

            for vacancy in vacancies_by_project:
                candidates_by_vacancy = await self._read_many_candidate_cards(
                    self.ReadManyCandidateCardsRequest(
                        vacancy_id=vacancy.id,
                    )
                )
                candidates_by_project.extend(candidates_by_vacancy)
                candidates_by_vacancies[vacancy.id] = candidates_by_vacancy

            project_statistics = self.calculate_project_statistics(
                self.CalculateProjectStatisticsRequest(
                    candidates_by_project=candidates_by_project,
                    vacancies_by_project=vacancies_by_project,
                )
            )

            _ = await self._project_repo.update_project(
                self._project_repo.UpdateProjectRequest(
                    id=request.project_id,
                    statistics=UpdateValue(value=project_statistics),
                )
            )

            del candidates_by_project
            del vacancies_by_project

            for vacancy_id, candidates_by_vacancy in candidates_by_vacancies.items():
                criteria_by_vacancy = await self._read_many_criteria_by_vacancy(
                    self.ReadManyCriteriaByVacancyRequest(
                        vacancy_id=vacancy_id,
                    )
                )
                stop_factors_by_vacancy = await self._read_many_stop_factors_by_vacancy(
                    self.ReadManyStopFactorsByVacancyRequest(
                        vacancy_id=vacancy_id,
                    )
                )

                candidate_scores: list[float] = []
                for candidate in candidates_by_vacancy:
                    if (
                        not candidate.criteria
                        and not candidate.stop_factors
                        or candidate.analysis_status != CandidateAnalysisStatusEnum.SUCCESS
                    ):
                        continue

                    try:
                        res = self._score_calculation_service.calculate_score_from_objects(
                            ScoreCalculationService.CalculateScoreFromObjectsRequest(
                                criteria=criteria_by_vacancy,
                                stop_factors=stop_factors_by_vacancy,
                                criteria_analysis=candidate.criteria or {},
                                stop_factors_analysis=candidate.stop_factors or {},
                            )
                        )
                        candidate_scores.append(res.score)
                    except Exception as e:
                        log.warning(f"failed to calculate score for candidate {candidate.id}: {e}")
                        continue

                _ = await self.calculate_and_update_statistics_by_vacancy(
                    self.CalculateAndUpdateStatisticsByVacancyRequest(
                        vacancy_id=vacancy_id,
                        candidates_by_vacancy=candidates_by_vacancy,
                        candidates_scores=candidate_scores,
                        criteria_by_vacancy=criteria_by_vacancy,
                        stop_factors_by_vacancy=stop_factors_by_vacancy,
                        project_statistics=project_statistics,
                    )
                )
            return
        except Exception as e:
            log.error("failed to calculate and update many statistics by project", err=e)
            raise StatisticsServiceError("error") from e

    @span(op="statistics_service", name="calculate_and_update_all_statistics")
    async def _calculate_and_update_all_statistics(self) -> None:
        try:
            clog = log.bind(trace_id=self.trace_id)
            users = await self._user_service.read_all()
            clog.info("retrieved all users")
            for user in users:
                try:
                    projects = await self._read_many_projects_by_user(
                        self.ReadManyProjectsByUserRequest(
                            user_id=user.id,
                        )
                    )
                    clog.info("retrieved all project for user", user_id=user.id)
                    for project in projects:
                        try:
                            await self.calculate_and_update_many_statistics_by_project(
                                self.CalculateAndUpdateManyStatisticsByProjectRequest(
                                    project_id=project.id,
                                )
                            )
                        except Exception as e:
                            log.error("failed to calculate and update many statistics by project, skip project", err=e)
                    clog.info("calculated and updated all statistics for user", user_id=user.id)
                except Exception as e:
                    log.error("failed to calculate and update all statistics for user", err=e)
            clog.info("calculated and updated all statistics")
        except Exception as e:
            log.error("failed to calculate and update all statistics", err=e)
            raise StatisticsServiceError("unknown error") from e

    @span(op="statistics_service", name="start")
    async def start(self) -> None:
        """Start the statistics service in background"""
        if self._running:
            log.warning("statistics service already running")
            return

        log.info("starting statistics service")
        self._running = True
        self._task = asyncio.create_task(self._run())
        log.info("data sync service started")

    @span(op="data_sync_service", name="stop")
    async def stop(self) -> None:
        """Stop the statistics service"""
        if not self._running:
            log.warning("statistics service not running")
            return

        log.info("stopping statistics service")
        self._running = False

        if self._task:
            _ = self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                log.debug("statistics service task cancelled")

        log.info("statistics service stopped")

    async def _run(self) -> None:
        """Main loop for updating statistics"""
        try:
            clog = log.bind(trace_id=self.trace_id)
            while self._running:
                try:
                    await self._calculate_and_update_all_statistics()
                    clog.info(
                        f"statistics service calculated and updated, sleeping for {self._sleep_between_updates_sec} seconds"
                    )
                    await asyncio.sleep(self._sleep_between_updates_sec)
                except StatisticsServiceError as e:
                    clog.error("calculation error, retrying in 5 seconds", error=str(e))
                    await asyncio.sleep(5)
                except asyncio.CancelledError as e:
                    log.info("statistics service cancelled")
                    raise e
                except Exception as e:
                    clog.error("unexpected error in update statistics loop", error=str(e), exc_info=True)
                    await asyncio.sleep(5)

        except asyncio.CancelledError:
            log.info("statistics service cancelled")
            raise
        except Exception as e:
            log.error("fatal error in statistics service", error=str(e), exc_info=True)

    # ===

    def _statistics_by_vacancy_key(self, vacancy_id: VacancyID) -> Key:
        return self._ks.key("vacancy_id", str(vacancy_id))

    def _project_set_by_vacancy_key(self, project_id: ProjectID) -> Key:
        return self._ks.key("project_set", str(project_id))
