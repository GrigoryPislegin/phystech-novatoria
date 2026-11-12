from datetime import datetime
from typing import final

import structlog
from pydantic import BaseModel

from nanimai_platform.domain.operation.operation import (
    GenerateAnalysisOperation,
    Operation,
    OperationStatus,
    OperationUsageReport,
    ParseCandidateOperation,
    ParseVacancyOperation,
)
from nanimai_platform.domain.scalar.scalars import AnalysisID, CandidateID, OperationID, ProjectID, UserID, VacancyID
from nanimai_platform.protocols.internal.repository.candidate import (
    CandidateNotFoundError,
    CandidateRepositoryProtocol,
)
from nanimai_platform.protocols.internal.repository.operation import (
    OperationNotFoundError,
    OperationRepositoryError,
    OperationRepositoryProtocol,
    OperationValidateError,
    ReadOperationError,
    UnknownOperationTypeError,
)
from nanimai_platform.protocols.internal.repository.project import (
    ProjectNotFoundError,
    ProjectRepositoryProtocol,
)
from nanimai_platform.protocols.internal.repository.vacancy import (
    VacancyNotFoundError,
    VacancyRepositoryProtocol,
)
from nanimai_platform.services.update_stream.service import EventType, UpdateStreamService
from nanimai_platform.utils.asyncio_background import launch_background
from nanimai_platform.utils.logging_span import span

log = structlog.stdlib.get_logger("app.service.OperationService")


class OperationServiceError(Exception): ...


class OperationServiceProjectNotFoundError(Exception): ...


class OperationServiceVacancyNotFoundError(Exception): ...


class OperationServiceCandidateNotFoundError(Exception): ...


class OperationServiceOperationNotFoundError(Exception): ...


class OperationServiceInvalidDataError(Exception): ...


@final
class OperationService:
    def __init__(
        self,
        operation_repo: OperationRepositoryProtocol,
        project_repo: ProjectRepositoryProtocol,
        vacancy_repo: VacancyRepositoryProtocol,
        candidate_repo: CandidateRepositoryProtocol,
        update_stream: UpdateStreamService,
    ):
        self._operation_repo = operation_repo
        self._project_repo = project_repo
        self._vacancy_repo = vacancy_repo
        self._candidate_repo = candidate_repo
        self._update_stream = update_stream

    class CreateParseVacancyOperationRequest(BaseModel):
        project_id: ProjectID
        filepath: str
        finished_at: datetime | None = None
        status: OperationStatus = OperationStatus.PENDING
        usage: list[OperationUsageReport] = []
        created_vacancy_id: VacancyID | None = None

    @span(op="operation_service", name="create_parse_vacancy")
    async def create_parse_vacancy(
        self,
        request: CreateParseVacancyOperationRequest,
    ) -> ParseVacancyOperation:
        try:
            operation = await self._operation_repo.create_parse_vacancy_operation(
                OperationRepositoryProtocol.CreateParseVacancyOperationRequest(
                    project_id=request.project_id,
                    filepath=request.filepath,
                    finished_at=request.finished_at,
                    status=request.status,
                    usage=request.usage,
                    created_vacancy_id=request.created_vacancy_id,
                )
            )

            @launch_background
            async def update_cache():
                await self._update_stream.push(
                    UpdateStreamService.PushRequest(
                        user_id=operation.user_id,
                        event_type=EventType.CREATED,
                        entity=operation,
                    )
                )

            update_cache()

            return operation
        except ProjectNotFoundError as e:
            log.error("failed to find project", err=e)
            raise OperationServiceProjectNotFoundError("project not found") from e
        except OperationRepositoryError as e:
            log.error("failed to create operation", err=e)
            raise OperationServiceError("failed to create") from e
        except Exception as e:
            log.error("failed to create operation", err=e)
            raise OperationServiceError("unknown error") from e

    class CreateParseCandidateOperationRequest(BaseModel):
        vacancy_id: VacancyID
        filepath: str
        finished_at: datetime | None = None
        status: OperationStatus = OperationStatus.PENDING
        usage: list[OperationUsageReport] = []
        created_candidate_id: CandidateID | None = None

    @span(op="operation_service", name="create_parse_candidate")
    async def create_parse_candidate(
        self,
        request: CreateParseCandidateOperationRequest,
    ) -> ParseCandidateOperation:
        try:
            log.debug("creating parse candidate operation", operation=request)
            operation = await self._operation_repo.create_parse_candidate_operation(
                OperationRepositoryProtocol.CreateParseCandidateOperationRequest(
                    vacancy_id=request.vacancy_id,
                    filepath=request.filepath,
                    finished_at=request.finished_at,
                    status=request.status,
                    usage=request.usage,
                    created_candidate_id=request.created_candidate_id,
                )
            )

            @launch_background
            async def update_cache():
                await self._update_stream.push(
                    UpdateStreamService.PushRequest(
                        user_id=operation.user_id,
                        event_type=EventType.CREATED,
                        entity=operation,
                    )
                )

            update_cache()

            return operation
        except VacancyNotFoundError as e:
            log.error("failed to find vacancy", err=e)
            raise OperationServiceVacancyNotFoundError("vacancy not found") from e
        except OperationRepositoryError as e:
            log.error("failed to create operation", err=e)
            raise OperationServiceError("failed to create") from e
        except Exception as e:
            log.error("failed to create operation", err=e)
            raise OperationServiceError("unknown error") from e

    class CreateGenerateAnalysisOperationRequest(BaseModel):
        candidate_id: CandidateID
        finished_at: datetime | None = None
        status: OperationStatus = OperationStatus.PENDING
        usage: list[OperationUsageReport] = []
        created_analysis_id: AnalysisID | None = None

    @span(op="operation_service", name="create_generate_analysis")
    async def create_generate_analysis(
        self,
        request: CreateGenerateAnalysisOperationRequest,
    ) -> GenerateAnalysisOperation:
        try:
            operation = await self._operation_repo.create_generate_analysis_operation(
                OperationRepositoryProtocol.CreateGenerateAnalysisOperationRequest(
                    candidate_id=request.candidate_id,
                    finished_at=request.finished_at,
                    status=request.status,
                    usage=request.usage,
                    created_analysis_id=request.created_analysis_id,
                )
            )

            @launch_background
            async def update_cache():
                await self._update_stream.push(
                    UpdateStreamService.PushRequest(
                        user_id=operation.user_id,
                        event_type=EventType.CREATED,
                        entity=operation,
                    )
                )

            update_cache()

            return operation
        except CandidateNotFoundError as e:
            log.error("failed to find candidate", err=e)
            raise OperationServiceCandidateNotFoundError("candidate not found") from e
        except OperationValidateError as e:
            log.error("failed to create operation due to validation error", err=e)
            raise OperationServiceInvalidDataError("invalid data") from e
        except OperationRepositoryError as e:
            log.error("failed to create operation", err=e)
            raise OperationServiceError("failed to create") from e
        except Exception as e:
            log.error("failed to create operation", err=e)
            raise OperationServiceError("unknown error") from e

    class ReadOperationRequest(BaseModel):
        id: OperationID

    @span(op="operation_service", name="read_operation")
    async def read(self, request: ReadOperationRequest) -> Operation:
        try:
            return await self._operation_repo.read_operation(
                OperationRepositoryProtocol.ReadOperationRequest(id=request.id)
            )
        except OperationValidateError as e:
            log.error("failed to read operation due to validation error", err=e)
            raise OperationServiceInvalidDataError("invalid data") from e
        except OperationNotFoundError as e:
            log.error("failed to find operation", err=e)
            raise OperationServiceOperationNotFoundError("failed to find") from e
        except UnknownOperationTypeError as e:
            log.error("failed to find operation", err=e)
            raise OperationServiceInvalidDataError("failed to validate with unknown type") from e
        except OperationRepositoryError as e:
            log.error("failed to read operation", err=e)
            raise OperationServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read operation", err=e)
            raise OperationServiceError("unknown error") from e

    class ReadManyOperationsRequest(BaseModel):
        operation_ids: list[OperationID]

    @span(op="operation_service", name="read_many_operations")
    async def read_many(self, request: ReadManyOperationsRequest) -> list[Operation | None]:
        try:
            return await self._operation_repo.read_many_operations(
                OperationRepositoryProtocol.ReadManyOperationsRequest(operation_ids=request.operation_ids)
            )
        except OperationValidateError as e:
            log.error("failed to read many operations due to validation error", err=e)
            raise OperationServiceInvalidDataError("invalid data") from e
        except OperationRepositoryError as e:
            log.error("failed to read many operations", err=e)
            raise OperationServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read many operations", err=e)
            raise OperationServiceError("unknown error") from e

    class UpdateParseVacancyOperationRequest(BaseModel):
        id: OperationID
        status: OperationStatus | None = None
        finished_at: datetime | None = None
        usage: list[OperationUsageReport] | None = None
        created_vacancy_id: VacancyID | None = None

    @span(op="operation_service", name="update_parse_vacancy")
    async def update_parse_vacancy(
        self,
        request: UpdateParseVacancyOperationRequest,
    ) -> ParseVacancyOperation:
        try:
            operation = await self._operation_repo.update_parse_vacancy_operation(
                OperationRepositoryProtocol.UpdateParseVacancyOperationRequest(
                    id=request.id,
                    status=request.status,
                    finished_at=request.finished_at,
                    usage=request.usage,
                    created_vacancy_id=request.created_vacancy_id,
                )
            )

            @launch_background
            async def update_cache():
                await self._update_stream.push(
                    UpdateStreamService.PushRequest(
                        user_id=operation.user_id,
                        event_type=EventType.UPDATED,
                        entity=operation,
                    )
                )

            update_cache()

            return operation
        except OperationValidateError as e:
            log.error("failed to update operation due to validation error", err=e)
            raise OperationServiceInvalidDataError("invalid data") from e
        except OperationNotFoundError as e:
            log.error("failed to find operation", err=e)
            raise OperationServiceOperationNotFoundError("failed to find") from e
        except OperationRepositoryError as e:
            log.error("failed to update operation", err=e)
            raise OperationServiceError("failed to update") from e
        except Exception as e:
            log.error("failed to update operation", err=e)
            raise OperationServiceError("unknown error") from e

    class UpdateParseCandidateOperationRequest(BaseModel):
        id: OperationID
        status: OperationStatus | None = None
        finished_at: datetime | None = None
        usage: list[OperationUsageReport] | None = None
        created_candidate_id: CandidateID | None = None

    @span(op="operation_service", name="update_parse_candidate")
    async def update_parse_candidate(
        self,
        request: UpdateParseCandidateOperationRequest,
    ) -> ParseCandidateOperation:
        try:
            operation = await self._operation_repo.update_parse_candidate_operation(
                OperationRepositoryProtocol.UpdateParseCandidateOperationRequest(
                    id=request.id,
                    status=request.status,
                    finished_at=request.finished_at,
                    usage=request.usage,
                    created_candidate_id=request.created_candidate_id,
                )
            )

            @launch_background
            async def update_cache():
                await self._update_stream.push(
                    UpdateStreamService.PushRequest(
                        user_id=operation.user_id,
                        event_type=EventType.UPDATED,
                        entity=operation,
                    )
                )

            update_cache()

            return operation
        except OperationValidateError as e:
            log.error("failed to update operation due to validation error", err=e)
            raise OperationServiceInvalidDataError("invalid data") from e
        except OperationNotFoundError as e:
            log.error("failed to find operation", err=e)
            raise OperationServiceOperationNotFoundError("failed to find") from e
        except OperationRepositoryError as e:
            log.error("failed to update operation", err=e)
            raise OperationServiceError("failed to update") from e
        except Exception as e:
            log.error("failed to update operation", err=e)
            raise OperationServiceError("unknown error") from e

    class UpdateGenerateAnalysisOperationRequest(BaseModel):
        id: OperationID
        status: OperationStatus | None = None
        finished_at: datetime | None = None
        usage: list[OperationUsageReport] | None = None
        created_analysis_id: AnalysisID | None = None

    @span(op="operation_service", name="update_generate_analysis")
    async def update_generate_analysis(
        self,
        request: UpdateGenerateAnalysisOperationRequest,
    ) -> GenerateAnalysisOperation:
        try:
            operation = await self._operation_repo.update_generate_analysis_operation(
                OperationRepositoryProtocol.UpdateGenerateAnalysisOperationRequest(
                    id=request.id,
                    status=request.status,
                    finished_at=request.finished_at,
                    usage=request.usage,
                    created_analysis_id=request.created_analysis_id,
                )
            )

            @launch_background
            async def update_cache():
                await self._update_stream.push(
                    UpdateStreamService.PushRequest(
                        user_id=operation.user_id,
                        event_type=EventType.UPDATED,
                        entity=operation,
                    )
                )

            update_cache()

            return operation
        except OperationValidateError as e:
            log.error("failed to update operation due to validation error", err=e)
            raise OperationServiceInvalidDataError("invalid data") from e
        except OperationNotFoundError as e:
            log.error("failed to find operation", err=e)
            raise OperationServiceOperationNotFoundError("failed to find") from e
        except OperationRepositoryError as e:
            log.error("failed to update operation", err=e)
            raise OperationServiceError("failed to update") from e
        except Exception as e:
            log.error("failed to update operation", err=e)
            raise OperationServiceError("unknown error") from e

    class DeleteOperationRequest(BaseModel):
        id: OperationID

    @span(op="operation_service", name="delete_operation")
    async def delete(self, request: DeleteOperationRequest) -> Operation:
        try:
            operation = await self._operation_repo.delete_operation(
                OperationRepositoryProtocol.DeleteOperationRequest(id=request.id)
            )

            @launch_background
            async def update_cache():
                await self._update_stream.push(
                    UpdateStreamService.PushRequest(
                        user_id=operation.user_id,
                        event_type=EventType.DELETED,
                        entity=operation,
                    )
                )

            update_cache()

            return operation
        except OperationValidateError as e:
            log.error("failed to delete operation due to validation error", err=e)
            raise OperationServiceInvalidDataError("invalid data") from e
        except OperationNotFoundError as e:
            log.error("failed to find operation", err=e)
            raise OperationServiceOperationNotFoundError("failed to find") from e
        except UnknownOperationTypeError as e:
            log.error("failed to find operation", err=e)
            raise OperationServiceInvalidDataError("failed to validate with unknown type") from e
        except OperationRepositoryError as e:
            log.error("failed to delete operation", err=e)
            raise OperationServiceError("failed to delete") from e
        except Exception as e:
            log.error("failed to delete operation", err=e)
            raise OperationServiceError("unknown error") from e

    class ReadManyByUserRequest(BaseModel):
        user_id: UserID

    @span(op="operation_service", name="read_many_by_user")
    async def read_many_by_user(self, request: ReadManyByUserRequest) -> list[Operation]:
        try:
            operations = await self._operation_repo.read_many_operations_by_user(
                OperationRepositoryProtocol.ReadManyOperationsByUserRequest(user_id=request.user_id)
            )
            return operations
        except ReadOperationError as e:
            log.error("failed to read operations", err=e)
            raise OperationServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read operations", err=e)
            raise OperationServiceError("unknown error") from e

    # class ListenUpdatesByUserRequest(BaseModel):
    #     user_id: UserID
