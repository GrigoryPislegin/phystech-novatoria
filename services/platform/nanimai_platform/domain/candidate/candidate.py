from enum import StrEnum

from pydantic import BaseModel, Field
from pydantic_core import Url
from pydantic_extra_types.currency_code import ISO4217 as CurrencyISO4217

from nanimai_platform.domain.scalar import CandidateID
from nanimai_platform.domain.scalar.scalars import AnalysisID, CriterionID, ProjectID, StopFactorID, UserID, VacancyID
from nanimai_platform.domain.skill import Skill
from nanimai_platform.domain.vacancy.vacancy import VacancyStageEnum
from nanimai_platform.utils import TimeBaseModel


class ExpectedSalary(BaseModel):
    currency: CurrencyISO4217 = Field(default=CurrencyISO4217("RUB"), description="currency in ISO 4217 format")
    value: int = Field(description="expected salary in the currency")


class ContactTypeEnum(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"


class CandidateAnalysisStatusEnum(StrEnum):
    """

                  ┌─►success
                  │ok
           ┌─►started
           │ok    │err
           │      └─►failed
    pending│
           │err
           └─►rejected

    """

    PENDING = "pending"
    STARTED = "started"
    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"


class CandidateSourceEnum(StrEnum):
    NANIMAI = "nanimai"
    HH = "hh"
    HH_SEARCH_CAMPAIGN = "hh_search_campaign"
    NANIMAI_JOBBOARD = "nanimai_jobboard"


class CriterionStatusEnum(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    FAIL = "fail"
    UNKNOWN = "unknown"


class CriterionAnalysis(BaseModel):
    score: float | None = Field(ge=0, le=1, description="score of candidate")
    status: CriterionStatusEnum | None = Field(description="status of candidate")
    description: str | None = Field(description="description of criterion analysis")


class StopFactorAnalysis(BaseModel):
    status: bool | None = Field(description="if candidate has stop-factor or not")
    description: str | None = Field(description="description of stop-factor analysis")


class Candidate(TimeBaseModel):
    id: CandidateID = Field(description="candidate id")
    user_id: UserID = Field(description="candidate user id")
    project_id: ProjectID = Field(description="candidate project id")
    vacancy_id: VacancyID = Field(description="candidate vacancy id")
    resume: str = Field(description="candidate resume")
    name: str = Field(description="candidate name")
    phone_number: str | None = Field(description="candidate phone number")
    email: str | None = Field(description="candidate email")
    website: Url | None = Field(description="candidate website")
    city: str | None = Field(description="candidate city")
    country: str | None = Field(description="candidate country")
    thumbnail_url: str = Field(description="candidate thumbnail url")
    experience: int = Field(description="candidate experience in months")
    expected_salary: ExpectedSalary | None = Field(description="candidate expected salary")
    notes: str = Field(description="candidate notes")
    dirty: bool = Field(description="candidate is dirty")
    source: CandidateSourceEnum = Field(description="candidate source")
    skills: list[Skill] = Field(description="candidate skills")
    status: VacancyStageEnum = Field(description="candidate status")
    status_history: set[VacancyStageEnum] = Field(description="unique set of statuses the candidate has been in")
    criteria: dict[CriterionID, CriterionAnalysis] = Field(description="candidate criteria")
    stop_factors: dict[StopFactorID, StopFactorAnalysis] = Field(description="candidate stop-factors")
    analysis_status: CandidateAnalysisStatusEnum = Field(description="candidate analysis status")
    contacts: dict[ContactTypeEnum, str] = Field(default_factory=dict, description="candidate contacts map")


class CandidateCard(TimeBaseModel):
    id: CandidateID = Field(description="candidate id")
    user_id: UserID = Field(description="candidate user id")
    project_id: ProjectID = Field(description="candidate project id")
    vacancy_id: VacancyID = Field(description="candidate vacancy id")

    name: str = Field(description="candidate name")
    experience: int = Field(description="candidate experience in months")
    expected_salary: ExpectedSalary | None = Field(default=None, description="candidate expected salary")
    thumbnail_url: str = Field(description="candidate thumbnail url")
    source: CandidateSourceEnum = Field(description="candidate source")
    status: VacancyStageEnum = Field(description="candidate status")
    status_history: set[VacancyStageEnum] = Field(description="unique set of statuses the candidate has been in")
    notes_preview: str = Field(description="candidate notes preview")
    dirty: bool = Field(description="candidate is dirty")

    analysis_id: AnalysisID | None = Field(default=None, description="candidate last analysis id", deprecated=True)
    score: float | None = Field(default=None, description="candidate last analysis score", deprecated=True)

    criteria: dict[CriterionID, CriterionAnalysis] = Field(description="candidate criteria")
    stop_factors: dict[StopFactorID, StopFactorAnalysis] = Field(description="candidate stop-factors")
    analysis_status: CandidateAnalysisStatusEnum = Field(description="candidate analysis status")
    contacts: dict[ContactTypeEnum, str] = Field(default_factory=dict, description="candidate contacts map")
