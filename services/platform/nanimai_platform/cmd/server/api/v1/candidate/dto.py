from datetime import datetime
from typing import Annotated

from pydantic import Field
from pydantic_core import Url
from pydantic_extra_types.currency_code import ISO4217

from nanimai_platform.cmd.server.api.common import common_dto
from nanimai_platform.cmd.server.utils.dtobase import DTOBase
from nanimai_platform.domain import ContactTypeEnum
from nanimai_platform.domain.candidate.candidate import Candidate, CandidateSourceEnum, CriterionStatusEnum
from nanimai_platform.domain.scalar import CandidateID, VacancyID
from nanimai_platform.domain.scalar.scalars import AnalysisID, CriterionID, ProjectID, StopFactorID, UserID


class ExpectedSalaryDTO(DTOBase):
    currency: Annotated[ISO4217, str]
    value: int


class CandidateResponseExpectedSalaryDTO(ExpectedSalaryDTO): ...


class AnalysisDTO(DTOBase):
    id: AnalysisID
    created_at: datetime
    updated_at: datetime
    pros: list[str]
    cons: list[str]
    comments: list[str]
    score: int


class StatisticsContainerDTO(DTOBase):
    total: int = 0
    today_increase: int = 0


class StatisticsDTO(DTOBase):
    all_candidates: StatisticsContainerDTO = Field(default_factory=StatisticsContainerDTO)
    delegated_candidates: StatisticsContainerDTO = Field(default_factory=StatisticsContainerDTO)
    platform_candidates: StatisticsContainerDTO = Field(default_factory=StatisticsContainerDTO)
    dirty_candidates: StatisticsContainerDTO = Field(default_factory=StatisticsContainerDTO)


class CandidateStatisticsResponseStatisticsDTO(StatisticsDTO): ...


class CriterionAnalysisDTO(DTOBase):
    score: float | None = Field(ge=0, le=1, description="score of candidate")
    status: CriterionStatusEnum | None = Field(description="status of candidate")
    description: str | None = Field(description="description of criterion analysis")


class CandidateResponseCriterionAnalysisDTO(CriterionAnalysisDTO): ...


class StopFactorAnalysisDTO(DTOBase):
    status: bool | None
    description: str | None


class CandidateResponseDTO(DTOBase):
    id: CandidateID
    created_at: datetime
    updated_at: datetime
    user_id: UserID
    project_id: ProjectID
    vacancy_id: VacancyID
    resume: str
    name: str
    phone_number: str | None
    email: str | None
    website: Url | None
    city: str | None
    country: str | None
    thumbnail_url: str
    experience: int
    expected_salary: CandidateResponseExpectedSalaryDTO | None
    notes: str
    dirty: bool
    source: CandidateSourceEnum
    skills: list[str]
    status: common_dto.VacancyColumnEnum
    last_analysis: AnalysisDTO | None
    criteria: dict[CriterionID, CandidateResponseCriterionAnalysisDTO] | None
    stop_factors: dict[StopFactorID, StopFactorAnalysisDTO] | None
    contacts: dict[ContactTypeEnum, str]

    @staticmethod
    def from_domain(candidate: Candidate) -> "CandidateResponseDTO":
        return CandidateResponseDTO(
            id=candidate.id,
            created_at=candidate.created_at,
            updated_at=candidate.updated_at,
            user_id=candidate.user_id,
            project_id=candidate.project_id,
            vacancy_id=candidate.vacancy_id,
            resume=candidate.resume,
            name=candidate.name,
            city=candidate.city,
            country=candidate.country,
            phone_number=candidate.phone_number,
            email=candidate.email,
            website=candidate.website,
            thumbnail_url=candidate.thumbnail_url,
            experience=candidate.experience,
            expected_salary=CandidateResponseExpectedSalaryDTO(
                currency=candidate.expected_salary.currency,
                value=candidate.expected_salary.value,
            )
            if candidate.expected_salary is not None
            else None,
            notes=candidate.notes,
            dirty=candidate.dirty,
            source=candidate.source,
            skills=[s.title for s in candidate.skills],
            status=candidate.status,
            last_analysis=None,  # Теперь всегда None
            criteria={
                id: CandidateResponseCriterionAnalysisDTO(
                    score=value.score, status=value.status, description=value.description
                )
                for id, value in candidate.criteria.items()
            }
            if candidate.criteria
            else None,
            stop_factors={
                id: StopFactorAnalysisDTO(status=value.status, description=value.description)
                for id, value in candidate.stop_factors.items()
            }
            if candidate.stop_factors
            else None,
            contacts=candidate.contacts,
        )


class GetAllCandidatesResponseDTO(DTOBase):
    candidates: list[CandidateResponseDTO]


class PostCandidateRequestDTO(DTOBase):
    vacancy_id: VacancyID
    resume: str
    name: str = Field(min_length=1, max_length=60)
    phone_number: str | None = None
    email: str | None = None
    website: Url | None = None
    city: str | None = Field(max_length=100, default=None)
    country: str | None = Field(max_length=100, default=None)
    experience: int = 0
    expected_salary: ExpectedSalaryDTO | None = None
    notes: str = Field(max_length=2000, default="")
    skills: list[str]
    # criteria: dict[CriterionID, CriterionAnalysisDTO] | None  # Пока запрещаем создавать
    # stop_factors: dict[StopFactorID, StopFactorAnalysisDTO] | None  # Пока запрещаем создавать


class PutCandidateRequestDTO(DTOBase):
    resume: str | None = None
    name: str | None = Field(min_length=1, max_length=60, default=None)
    phone_number: str | None = None
    email: str | None = None
    website: Url | None = None
    city: str | None = Field(max_length=100, default=None)
    country: str | None = Field(max_length=100, default=None)
    thumbnail_url: str | None = None
    experience: int | None = None
    expected_salary: ExpectedSalaryDTO | None = None
    notes: str | None = Field(max_length=2000, default=None)
    dirty: bool | None = None
    source: CandidateSourceEnum | None = None
    skills: list[str] | None = None
    status: common_dto.VacancyColumnEnum | None = None


class PutCandidateCriterionRequestDTO(DTOBase):
    status: CriterionStatusEnum | None = None
    description: str | None = None


class PutCandidateCriterionDTO(DTOBase):
    criterion_id: CriterionID
    status: CriterionStatusEnum | None = None
    description: str | None = None


class PutCandidateManyCriteriaRequestDTO(DTOBase):
    criteria: list[PutCandidateCriterionDTO]


class PutCandidateStopFactorRequestDTO(DTOBase):
    status: bool | None = None
    description: str | None = None


class PutCandidateStopFactorDTO(DTOBase):
    stop_factor_id: StopFactorID
    status: bool | None = None
    description: str | None = None


class PutCandidateManyStopFactorsRequestDTO(DTOBase):
    stop_factors: list[PutCandidateStopFactorDTO]


class GetCandidateStatisticsResponseDTO(DTOBase):
    statistics: CandidateStatisticsResponseStatisticsDTO


class GetResumeDownloadLinkResponseDTO(DTOBase):
    download_link: str
