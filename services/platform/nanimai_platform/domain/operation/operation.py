from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from nanimai_platform.domain.scalar import AnalysisID, CandidateID, OperationID, ProjectID, VacancyID
from nanimai_platform.domain.scalar.scalars import UserID
from nanimai_platform.utils.pydantic_timebase import TimeBaseModel


class OperationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"


class OperationKind(StrEnum):
    PARSE_VACANCY = "parse_vacancy"
    PARSE_CANDIDATE = "parse_candidate"
    GENERATE_ANALYSIS = "generate_analysis"


class OperationUsageReport(BaseModel):
    model: str = Field(
        description=("model name"),
    )

    input_tokens: int = Field(
        description=("number of input tokens"),
    )

    output_tokens: int = Field(
        description=("number of output tokens"),
    )

    time_spent: float = Field(
        description=("time spent in seconds"),
    )


class BaseOperation(TimeBaseModel):
    id: OperationID = Field(description=("operation id"))
    user_id: UserID

    finished_at: datetime | None = Field(
        description=("datetime when operation has finished"),
    )

    status: OperationStatus = Field(
        description=("operation status"),
    )

    usage: list[OperationUsageReport] = Field(
        description=("operation resource usage reports"),
    )


class ParseVacancyOperation(BaseOperation):
    kind: Literal[OperationKind.PARSE_VACANCY] = OperationKind.PARSE_VACANCY

    project_id: ProjectID
    filepath: str

    created_vacancy_id: VacancyID | None


class ParseCandidateOperation(BaseOperation):
    kind: Literal[OperationKind.PARSE_CANDIDATE] = OperationKind.PARSE_CANDIDATE

    vacancy_id: VacancyID
    filepath: str

    created_candidate_id: CandidateID | None


class GenerateAnalysisOperation(BaseOperation):
    kind: Literal[OperationKind.GENERATE_ANALYSIS] = OperationKind.GENERATE_ANALYSIS

    candidate_id: CandidateID

    created_analysis_id: AnalysisID | None


type Operation = ParseVacancyOperation | ParseCandidateOperation | GenerateAnalysisOperation
