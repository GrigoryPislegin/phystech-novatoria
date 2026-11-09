from datetime import date, datetime
from typing import Annotated

from pydantic_extra_types.currency_code import ISO4217

from nanimai_platform.cmd.server.api.common import common_dto
from nanimai_platform.cmd.server.utils.dtobase import DTOBase
from nanimai_platform.domain import (
    CandidateCriterionStopFactorStatusStatistics,
    CandidateSalaryStatistics,
    CandidateSourceEnum,
    CriterionID,
    CriterionStatusEnum,
    ProjectID,
    Statistics,
    StatisticsID,
    StopFactorID,
    UserID,
    VacancyID,
)


class ProjectStatisticsDTO(DTOBase):
    """DTO for ProjectStatistics domain model."""

    total_candidates: int
    total_vacancies: int
    active_vacancies: int


class VacancyCandidatesStatisticsDTO(DTOBase):
    """DTO for VacancyCandidatesStatistics domain model."""

    total_candidates: int
    total_today_increase: int
    platform_candidates: int
    platform_today_increase: int
    hh_candidates: int
    hh_today_increase: int
    total_dirty_candidates: int


class CandidateSourcesCountDTO(DTOBase):
    """DTO for CandidateSourcesCount domain model."""

    hh: int
    platform: int
    hh_search_campaign: int
    nanimai_jobboard: int

    @classmethod
    def from_domain(cls, statistics: dict[CandidateSourceEnum, int]) -> "CandidateSourcesCountDTO":
        return cls(
            hh=statistics.get(CandidateSourceEnum.HH, 0),
            platform=statistics.get(CandidateSourceEnum.NANIMAI, 0),
            hh_search_campaign=statistics.get(CandidateSourceEnum.HH_SEARCH_CAMPAIGN, 0),
            nanimai_jobboard=statistics.get(CandidateSourceEnum.NANIMAI_JOBBOARD, 0),
        )


class CandidateDateIncreaseStatisticsDTO(DTOBase):
    """DTO for date increase statistics."""

    bucket: date
    value: CandidateSourcesCountDTO


class CandidateScoreStatisticsDTO(DTOBase):
    """DTO for score statistics."""

    bucket: int
    value: int


class CriterionStatusStatisticsDTO(DTOBase):
    """DTO for criterion status statistics."""

    full: int = 0
    partial: int = 0
    fail: int = 0
    unknown: int = 0

    @classmethod
    def from_domain(cls, statistics: dict[CriterionStatusEnum, int]) -> "CriterionStatusStatisticsDTO":
        return cls(
            full=statistics.get(CriterionStatusEnum.FULL, 0),
            partial=statistics.get(CriterionStatusEnum.PARTIAL, 0),
            fail=statistics.get(CriterionStatusEnum.FAIL, 0),
            unknown=statistics.get(CriterionStatusEnum.UNKNOWN, 0),
        )


class StopFactorStatusStatisticsDTO(DTOBase):
    """DTO for stop factor status statistics."""

    triggered: int = 0
    not_triggered: int = 0

    @classmethod
    def from_domain(cls, statistics: dict[bool, int]) -> "StopFactorStatusStatisticsDTO":
        return cls(
            triggered=statistics.get(True, 0),
            not_triggered=statistics.get(False, 0),
        )


class CriterionStatusDetailDTO(DTOBase):
    """DTO for criterion status details."""

    id: CriterionID
    statistics: CriterionStatusStatisticsDTO


class StopFactorStatusDetailDTO(DTOBase):
    """DTO for stop factor status details."""

    id: StopFactorID
    statistics: StopFactorStatusStatisticsDTO


class CandidateStageStatisticsDTO(DTOBase):
    """DTO for candidate stage statistics."""

    bucket: common_dto.VacancyColumnEnum
    value: int


class CandidateCriterionStopFactorStatusStatisticsDTO(DTOBase):
    """DTO for candidate criterion and stop factor status statistics."""

    criterion_status_statistics: dict[CriterionID, CriterionStatusStatisticsDTO]
    stop_factor_status_statistics: dict[StopFactorID, StopFactorStatusStatisticsDTO]

    @classmethod
    def from_domain(
        cls, domain: CandidateCriterionStopFactorStatusStatistics
    ) -> "CandidateCriterionStopFactorStatusStatisticsDTO":
        criterion_stats = {
            criterion_id: CriterionStatusStatisticsDTO.from_domain(status.statistics)
            for criterion_id, status in domain.criterion_status_statistics.items()
        }

        stop_factor_stats = {
            stop_factor_id: StopFactorStatusStatisticsDTO.from_domain(status.statistics)
            for stop_factor_id, status in domain.stop_factor_status_statistics.items()
        }

        return cls(criterion_status_statistics=criterion_stats, stop_factor_status_statistics=stop_factor_stats)


class CandidateSalaryStatisticsDTO(DTOBase):
    currency: Annotated[ISO4217, str]
    count: int
    average: float
    median: float

    @classmethod
    def from_domain(cls, domain: CandidateSalaryStatistics) -> "CandidateSalaryStatisticsDTO":
        return cls(
            currency=domain.currency,
            count=domain.count,
            average=domain.average,
            median=domain.median,
        )


class StatisticsResponseDTO(DTOBase):
    """DTO for Statistics domain model."""

    id: StatisticsID
    user_id: UserID
    project_id: ProjectID
    vacancy_id: VacancyID

    created_at: datetime
    updated_at: datetime

    project_statistics: ProjectStatisticsDTO
    vacancy_statistics: VacancyCandidatesStatisticsDTO
    score_statistics: list[CandidateScoreStatisticsDTO]
    stage_statistics: list[CandidateStageStatisticsDTO]
    salary_statistics: CandidateSalaryStatisticsDTO
    criterion_stop_factor_status_statistics: CandidateCriterionStopFactorStatusStatisticsDTO
    date_increase_statistics: list[CandidateDateIncreaseStatisticsDTO]

    @classmethod
    def from_domain(cls, statistics: Statistics) -> "StatisticsResponseDTO":
        return cls(
            id=statistics.id,
            user_id=statistics.user_id,
            project_id=statistics.project_id,
            vacancy_id=statistics.vacancy_id,
            created_at=statistics.created_at,
            updated_at=statistics.updated_at,
            project_statistics=ProjectStatisticsDTO(
                total_candidates=statistics.project_statistics.total_candidates,
                total_vacancies=statistics.project_statistics.total_vacancies,
                active_vacancies=statistics.project_statistics.active_vacancies,
            ),
            vacancy_statistics=VacancyCandidatesStatisticsDTO(
                total_candidates=statistics.vacancy_statistics.total_candidates,
                total_today_increase=statistics.vacancy_statistics.total_today_increase,
                platform_candidates=statistics.vacancy_statistics.platform_candidates,
                platform_today_increase=statistics.vacancy_statistics.platform_today_increase,
                hh_candidates=statistics.vacancy_statistics.hh_candidates,
                hh_today_increase=statistics.vacancy_statistics.hh_today_increase,
                total_dirty_candidates=statistics.vacancy_statistics.total_dirty_candidates,
            ),
            score_statistics=[
                CandidateScoreStatisticsDTO(
                    bucket=bucket,
                    value=score,
                )
                for bucket, score in statistics.score_statistics.statistics.items()
            ],
            stage_statistics=[
                CandidateStageStatisticsDTO(bucket=bucket, value=value)
                for bucket, value in statistics.stage_statistics.statistics.items()
            ],
            salary_statistics=CandidateSalaryStatisticsDTO.from_domain(statistics.salary_statistics),
            criterion_stop_factor_status_statistics=CandidateCriterionStopFactorStatusStatisticsDTO.from_domain(
                statistics.criterion_stop_factor_status_statistics
            ),
            date_increase_statistics=[
                CandidateDateIncreaseStatisticsDTO(bucket=bucket, value=CandidateSourcesCountDTO.from_domain(score))
                for bucket, score in statistics.date_increase_statistics.statistics.items()
            ],
        )


class ManyStatisticsResponseDTO(DTOBase):
    """DTO for multiple statistics responses."""

    many_statistics: list[StatisticsResponseDTO]

    @classmethod
    def from_domain(cls, statistics_list: list[Statistics]) -> "ManyStatisticsResponseDTO":
        return cls(many_statistics=[StatisticsResponseDTO.from_domain(statistics) for statistics in statistics_list])
