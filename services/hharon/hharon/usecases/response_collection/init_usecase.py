from dataclasses import dataclass
from datetime import UTC, datetime
from typing import final

import pydantic
import structlog

from hharon.domain.outbox_task import OutboxTaskType, ResponseCollectionPayload
from hharon.protocols import response_collection as response_collection_protocol
from hharon.protocols.outbox_task import OutboxContext
from hharon.usecases.outbox_task.usecase import OutboxUsecase

log = structlog.stdlib.get_logger("hharon.usecases.InitResponseCollection")


class InitResponseCollectionError(Exception):
    """Base exception class for InitResponseCollection errors."""


class InitResponseCollectionNotFoundError(InitResponseCollectionError):
    """Settings not found error."""


@final
@dataclass(slots=True)
class InitResponseCollection[SessionT]:
    _response_collection_repository: response_collection_protocol.ResponseCollectionRepositoryProtocol[SessionT]
    _outbox_usecase: OutboxUsecase[SessionT]

    class InitResponseCollectionRequest(pydantic.BaseModel):
        user_id: str
        vacancy_id: str
        hh_vacancy_id: str
        hh_collections: list[str]

    class InitResponseCollectionResponse(pydantic.BaseModel):
        vacancy_id: str

    async def init(self, request: InitResponseCollectionRequest) -> InitResponseCollectionResponse:
        """Setup response collection settings and create task.

        Args:
            request: Request with settings data

        Returns:
            Response with settings_id and task_id

        Raises:
            InitResponseCollectionError: On unexpected errors
        """
        try:
            async with self._response_collection_repository.context() as session:
                # Check if settings already exist for this vacancy
                settings = await self._response_collection_repository.get_settings_by_vacancy(
                    session,
                    response_collection_protocol.ResponseCollectionRepositoryProtocol.GetSettingsByVacancyRequest(
                        vacancy_id=request.vacancy_id,
                    ),
                )

                if settings is None:
                    settings = await self._response_collection_repository.create_settings(
                        session,
                        response_collection_protocol.ResponseCollectionRepositoryProtocol.CreateSettingsRequest(
                            user_id=request.user_id,
                            vacancy_id=request.vacancy_id,
                            hh_vacancy_id=request.hh_vacancy_id,
                            hh_collections=request.hh_collections,
                        ),
                    )
                    log.info("created new settings", settings_id=settings.id)
                else:
                    log.info("settings already exist, creating new task", settings_id=settings.id)

                # Create task for response collection
                payload = ResponseCollectionPayload(settings_id=settings.id)
                task = await self._outbox_usecase.schedule_task(
                    ctx=OutboxContext(session=session),
                    request=OutboxUsecase[SessionT].ScheduleTaskRequest(
                        task_type=OutboxTaskType.RESPONSE_COLLECTION,
                        payload=payload.model_dump(mode="json"),
                        available_at=datetime.now(UTC),  # Start immediately
                    ),
                )

                log.info("created response collection task", task_id=task.id, settings_id=settings.id)
                return self.InitResponseCollectionResponse(vacancy_id=settings.vacancy_id)

        except Exception as e:
            log.exception("unexpected error in init response collection", error=str(e))
            raise InitResponseCollectionError("unexpected error") from e
