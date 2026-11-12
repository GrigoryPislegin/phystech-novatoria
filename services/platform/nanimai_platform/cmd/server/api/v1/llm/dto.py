from typing import Annotated

from fastapi import UploadFile
from pydantic_extra_types.currency_code import ISO4217

from nanimai_platform.cmd.server.api.common import common_dto
from nanimai_platform.cmd.server.utils.dtobase import DTOBase
from nanimai_platform.domain.scalar.scalars import CandidateID, OperationID, ProjectID, VacancyID


class ErrorDTO(DTOBase):
    message: str


class OperationDTO(DTOBase):
    id: OperationID


class ParseMultipleCandidateResponseDTO(DTOBase):
    ops: list[OperationDTO | ErrorDTO]


class ParseMultipleVacancyResponseDTO(DTOBase):
    ops: list[OperationDTO | ErrorDTO]


class AnalyzeSingleCandidateForVacancyRequestDTO(DTOBase):
    candidate_id: CandidateID
    vacancy_id: VacancyID


class AnalyzeSingleCandidateForVacancyResponseDTO(DTOBase):
    op_id: OperationID


class AnalyzeMultipleCandidateForVacancyRequestDTO(DTOBase):
    vacancy_id: VacancyID
    candidate_ids: list[CandidateID]


class AnalyzeMultipleCandidateForVacancyResponseDTO(DTOBase):
    ops: list[OperationDTO | ErrorDTO]


class ParseCandidatesFormRequestDTO(DTOBase):
    vacancy_id: VacancyID
    files: list[UploadFile]


class ParseVacanciesFormRequestDTO(DTOBase):
    project_id: ProjectID
    files: list[UploadFile]


class SalaryAmountRangeDTO(DTOBase):
    currency: Annotated[ISO4217, str]
    min: int | None
    max: int | None


class VacancyStageDTO(DTOBase):
    kind: common_dto.VacancyColumnEnum
    shown: bool = True


class PublishToDTO(DTOBase):
    hh: bool = False
    # add more platforms when needed
