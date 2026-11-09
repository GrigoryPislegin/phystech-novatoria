from datetime import datetime
from typing import Literal

from nanimai_platform.cmd.server.utils.dtobase import DTOBase
from nanimai_platform.domain import (
    AnalysisID,
    CandidateID,
    OperationID,
    OperationKind,
    OperationStatus,
    ProjectID,
    VacancyID,
)


class BaseOperationResponseDTO(DTOBase):
    id: OperationID
    created_at: datetime
    finished_at: datetime | None
    status: OperationStatus


class OperationProjectDTO(DTOBase):
    id: ProjectID
    title: str


class OperationVacancyDTO(DTOBase):
    id: VacancyID
    title: str


class OperationCandidateDTO(DTOBase):
    id: CandidateID
    name: str


class OperationAnalysisDTO(DTOBase):
    id: AnalysisID
    score: int


class ParseVacancyOperationResponseDTO(BaseOperationResponseDTO):
    kind: Literal[OperationKind.PARSE_VACANCY] = OperationKind.PARSE_VACANCY
    project: OperationProjectDTO
    created_vacancy: OperationVacancyDTO | None


class ParseCandidateOperationResponseDTO(BaseOperationResponseDTO):
    kind: Literal[OperationKind.PARSE_CANDIDATE] = OperationKind.PARSE_CANDIDATE
    vacancy: OperationVacancyDTO
    created_candidate: OperationCandidateDTO | None


class GenerateAnalysisOperationResponseDTO(BaseOperationResponseDTO):
    kind: Literal[OperationKind.GENERATE_ANALYSIS] = OperationKind.GENERATE_ANALYSIS
    vacancy: OperationVacancyDTO
    candidate: OperationCandidateDTO
    created_analysis: OperationAnalysisDTO | None


class GetAllOperationsResponseDTO(DTOBase):
    operations: list[
        ParseVacancyOperationResponseDTO | ParseCandidateOperationResponseDTO | GenerateAnalysisOperationResponseDTO
    ]
