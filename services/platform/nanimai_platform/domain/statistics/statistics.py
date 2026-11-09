from datetime import date

from pydantic import BaseModel, Field
from pydantic_extra_types.currency_code import ISO4217 as CurrencyISO4217

from nanimai_platform.domain.candidate import CandidateSourceEnum, CriterionStatusEnum
from nanimai_platform.domain.project import ProjectStatistics
from nanimai_platform.domain.scalar.scalars import CriterionID, ProjectID, StatisticsID, StopFactorID, UserID, VacancyID
from nanimai_platform.domain.vacancy import VacancyStageEnum
from nanimai_platform.utils import TimeBaseModel


class VacancyCandidatesStatistics(BaseModel):
    total_candidates: int = Field(description="total number of candidates")
    total_today_increase: int = Field(description="today increase in number of candidates")

    platform_candidates: int = Field(description="number of platform candidates")
    platform_today_increase: int = Field(description="today increase in number of platform candidates")

    hh_candidates: int = Field(description="number of delegated candidates from hh")
    hh_today_increase: int = Field(description="today increase in number of delegated candidates from hh")

    total_dirty_candidates: int = Field(description="number of dirty candidates")
    dirty_today_increase: int = Field(description="today increase in number of dirty candidates")


class CandidateScoreStatistics(BaseModel):
    statistics: dict[int, int] = Field(description="number of candidates with scores(values) <= bucket(key)")


class CandidateStageStatistics(BaseModel):
    statistics: dict[VacancyStageEnum, int] = Field(
        description="candidate vacancy stage and number of candidates fit it"
    )


class CandidateCriterionStatus(BaseModel):
    statistics: dict[CriterionStatusEnum, int] = Field(
        description="candidate criterion status and number of candidates fit it"
    )


class CandidateStopFactorStatus(BaseModel):
    statistics: dict[bool, int] = Field(description="candidate stop-factor status and number of candidates fit it")


class CandidateCriterionStopFactorStatusStatistics(BaseModel):
    criterion_status_statistics: dict[CriterionID, CandidateCriterionStatus] = Field(
        description="all candidate criterion statuses"
    )
    stop_factor_status_statistics: dict[StopFactorID, CandidateStopFactorStatus] = Field(
        description="all candidate stop-factor statuses"
    )


class CandidateDateIncreaseStatistics(BaseModel):
    statistics: dict[date, dict[CandidateSourceEnum, int]] = Field(description="number of candidates by date")


class CandidateSalaryStatistics(BaseModel):
    currency: CurrencyISO4217 = Field(default=CurrencyISO4217("RUB"), description="currency in ISO 4217 format")
    count: int = Field(description="number of candidates")
    average: float = Field(description="average salary")
    median: float = Field(description="median salary")


class Statistics(TimeBaseModel):
    id: StatisticsID = Field(description="statistic id")
    user_id: UserID = Field(description="statistic user id")
    project_id: ProjectID = Field(description="statistic project id")
    vacancy_id: VacancyID = Field(description="statistic vacancy id")

    project_statistics: ProjectStatistics = Field(description="project statistics")
    vacancy_statistics: VacancyCandidatesStatistics = Field(description="vacancy statistics")
    score_statistics: CandidateScoreStatistics = Field(description="distribution of candidate scores by buckets")
    stage_statistics: CandidateStageStatistics = Field(description="distribution of candidate stages")
    salary_statistics: CandidateSalaryStatistics = Field(description="distribution of candidate salaries")
    criterion_stop_factor_status_statistics: CandidateCriterionStopFactorStatusStatistics = Field(
        description="distribution of candidate by criterion and stop-factor statuses"
    )
    date_increase_statistics: CandidateDateIncreaseStatistics = Field(
        description="increase in candidates by date (last 3 months)"
    )
