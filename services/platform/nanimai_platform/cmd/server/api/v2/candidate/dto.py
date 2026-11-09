from datetime import datetime

from nanimai_platform.cmd.server.api.common import common_dto
from nanimai_platform.cmd.server.utils.dtobase import DTOBase
from nanimai_platform.domain import ContactTypeEnum
from nanimai_platform.domain.candidate.candidate import CandidateSourceEnum, CriterionStatusEnum
from nanimai_platform.domain.scalar.scalars import (
    AnalysisID,
    CandidateID,
    CriterionID,
    ProjectID,
    StopFactorID,
    UserID,
    VacancyID,
)


class ExpectedSalaryDTO(DTOBase):
    currency: str
    value: int


class CandidateCardExpectedSalaryDTO(ExpectedSalaryDTO): ...


class CriterionAnalysisDTO(DTOBase):
    score: float | None
    status: CriterionStatusEnum | None
    description: str | None


class CandidateCardCriterionAnalysisDTO(CriterionAnalysisDTO): ...


class StopFactorAnalysisDTO(DTOBase):
    status: bool | None
    description: str | None


class CandidateCardDTO(DTOBase):
    id: CandidateID

    user_id: UserID
    project_id: ProjectID
    vacancy_id: VacancyID

    created_at: datetime
    updated_at: datetime

    name: str
    experience: int
    expected_salary: CandidateCardExpectedSalaryDTO | None
    thumbnail_url: str
    source: CandidateSourceEnum
    status: common_dto.VacancyColumnEnum
    notes_preview: str  # 30 символов
    dirty: bool

    score: float | None
    analysis_id: AnalysisID | None
    criteria: dict[CriterionID, CandidateCardCriterionAnalysisDTO]
    stop_factors: dict[StopFactorID, StopFactorAnalysisDTO]

    contacts: dict[ContactTypeEnum, str]


class GetAllCandidateCardsResponseDTO(DTOBase):
    candidates: list[CandidateCardDTO]
