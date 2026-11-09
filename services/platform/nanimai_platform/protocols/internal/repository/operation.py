from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from nanimai_platform.domain import (
    AnalysisID,
    CandidateID,
    OperationID,
    OperationKind,
    OperationStatus,
    OperationUsageReport,
    ProjectID,
    VacancyID,
)
from nanimai_platform.domain.operation import (
    GenerateAnalysisOperation,
    Operation,
    ParseCandidateOperation,
    ParseVacancyOperation,
)
from nanimai_platform.domain.scalar.scalars import UserID


class OperationRepositoryError(Exception): ...


class OperationValidateError(OperationRepositoryError): ...


class OperationNotFoundError(OperationRepositoryError): ...


class UnknownOperationTypeError(OperationRepositoryError): ...


class CreateOperationError(OperationRepositoryError): ...


class ReadOperationError(OperationRepositoryError): ...


class UpdateOperationError(OperationRepositoryError): ...


class DeleteOperationError(OperationRepositoryError): ...


class OperationRepositoryProtocol(ABC):
    @dataclass
    class CreateParseVacancyOperationRequest:
        project_id: ProjectID
        filepath: str

        finished_at: datetime | None
        status: OperationStatus
        usage: list[OperationUsageReport]
        created_vacancy_id: VacancyID | None
        kind: Literal[OperationKind.PARSE_VACANCY] = OperationKind.PARSE_VACANCY

    @abstractmethod
    async def create_parse_vacancy_operation(
        self,
        request: CreateParseVacancyOperationRequest,
    ) -> ParseVacancyOperation:
        """creates parse vacancy operation in repository

        Raises:
            CreateOperationError - not expected exception
            OperationValidateError - validation error
            VacancyNotFoundError - vacancy not found
        Returns:
            BaseOperation - created operation
        """
        ...

    @dataclass
    class CreateParseCandidateOperationRequest:
        vacancy_id: VacancyID
        filepath: str

        finished_at: datetime | None
        status: OperationStatus
        usage: list[OperationUsageReport]
        created_candidate_id: CandidateID | None
        kind: Literal[OperationKind.PARSE_CANDIDATE] = OperationKind.PARSE_CANDIDATE

    @abstractmethod
    async def create_parse_candidate_operation(
        self,
        request: CreateParseCandidateOperationRequest,
    ) -> ParseCandidateOperation:
        """creates parse candidate operation in repository

        Raises:
            CreateOperationError - not expected exception
            OperationValidateError - validation error
            CandidateNotFoundError - candidate not found
        Returns:
            BaseOperation - created operation
        """
        ...

    @dataclass
    class CreateGenerateAnalysisOperationRequest:
        candidate_id: CandidateID

        finished_at: datetime | None
        status: OperationStatus
        usage: list[OperationUsageReport]
        created_analysis_id: AnalysisID | None
        kind: Literal[OperationKind.GENERATE_ANALYSIS] = OperationKind.GENERATE_ANALYSIS

    @abstractmethod
    async def create_generate_analysis_operation(
        self,
        request: CreateGenerateAnalysisOperationRequest,
    ) -> GenerateAnalysisOperation:
        """creates generate analysis operation in repository

        Raises:
            CreateOperationError - not expected exception
            OperationValidateError - validation error
            AnalysisNotFoundErorr - analysis not found
        Returns:
            BaseOperation - created operation
        """
        ...

    @dataclass
    class ReadOperationRequest:
        id: OperationID

    @abstractmethod
    async def read_operation(self, request: ReadOperationRequest) -> Operation:
        """reads operation in repository

        Raises:
            ReadOperationError - not expected exception
            OperationValidateError - validation error
            OperationNotFoundError - operation not found
            UnknownOperationType - unknown type of operation
        Returns:
            Operation - read operation
        """
        ...

    @dataclass
    class UpdateParseVacancyOperationRequest:
        id: OperationID

        status: OperationStatus | None = None
        finished_at: datetime | None = None
        usage: list[OperationUsageReport] | None = None
        created_vacancy_id: VacancyID | None = None

    @abstractmethod
    async def update_parse_vacancy_operation(
        self,
        request: UpdateParseVacancyOperationRequest,
    ) -> ParseVacancyOperation:
        """updates parse vacancy operation in repository

        Raises:
            UpdateOperationError - not expected exception
            OperationValidateError - validation error
            OperationNotFoundError - operation not found
        Returns:
            BaseOperation - updated operation
        """
        ...

    @dataclass
    class UpdateParseCandidateOperationRequest:
        id: OperationID

        status: OperationStatus | None = None
        finished_at: datetime | None = None
        usage: list[OperationUsageReport] | None = None
        created_candidate_id: CandidateID | None = None

    @abstractmethod
    async def update_parse_candidate_operation(
        self,
        request: UpdateParseCandidateOperationRequest,
    ) -> ParseCandidateOperation:
        """updates parse candidate operation in repository

        Raises:
            UpdateOperationError - not expected exception
            OperationValidateError - validation error
            OperationNotFoundError - operation not found
        Returns:
            BaseOperation - updated operation
        """
        ...

    @dataclass
    class UpdateGenerateAnalysisOperationRequest:
        id: OperationID

        status: OperationStatus | None = None
        finished_at: datetime | None = None
        usage: list[OperationUsageReport] | None = None
        created_analysis_id: AnalysisID | None = None

    @abstractmethod
    async def update_generate_analysis_operation(
        self,
        request: UpdateGenerateAnalysisOperationRequest,
    ) -> GenerateAnalysisOperation:
        """updates generate analysis operation in repository

        Raises:
            UpdateOperationError - not expected exception
            OperationValidateError - validation error
            OperationNotFoundError - operation not found
        Returns:
            BaseOperation - updated operation
        """
        ...

    @dataclass
    class DeleteOperationRequest:
        id: OperationID

    @abstractmethod
    async def delete_operation(self, request: DeleteOperationRequest) -> Operation:
        """deletes operation in repository

        Raises:
            DeleteOperationError - not expected exception
            OperationValidateError - validation error
            OperationNotFoundError - operation not found
            UnknownOperationType - unknown type of operation
        Returns:
            Operation - deleted operation
        """
        ...

    @dataclass
    class ReadManyOperationsRequest:
        operation_ids: list[OperationID]

    @abstractmethod
    async def read_many_operations(self, request: ReadManyOperationsRequest) -> list[Operation | None]:
        """reads many operations in repository

        Raises:
            ReadOperationError - not expected exception
            OperationValidateError - validation error
            OperationNotFoundError - operation not found
        Returns:
            list[Operation | None] - list of operations or None if operation does not exist
        """
        ...

    @dataclass
    class ReadManyOperationsByUserRequest:
        user_id: UserID

    @abstractmethod
    async def read_many_operations_by_user(self, request: ReadManyOperationsByUserRequest) -> list[Operation]:
        """reads many operations by user in repository

        Raises:
            ReadOperationError - not expected exception
            OperationValidateError - validation error
        Returns:
            list[Operation] - list of operations
        """
        ...
