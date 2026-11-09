from typing import final

import pydantic
import structlog

from hharon.domain.response_collection import ResponseCollectionStatus
from hharon.protocols import response_collection as response_collection_protocol

log = structlog.stdlib.get_logger("hharon.usecases.CompleteResponseCollection")


class CompleteResponseCollectionError(Exception):
    """Base exception for CompleteResponseCollection errors."""


class CompleteResponseCollectionNotFoundError(CompleteResponseCollectionError):
    """Settings not found error."""


@final
class CompleteResponseCollection[SessionT]:
    def __init__(
        self,
        *,
        response_collection_repository: response_collection_protocol.ResponseCollectionRepositoryProtocol[SessionT],
    ) -> None:
        self._response_collection_repository = response_collection_repository

    class CompleteResponseCollectionRequest(pydantic.BaseModel):
        vacancy_id: str

    class CompleteResponseCollectionResponse(pydantic.BaseModel):
        vacancy_id: str
        status: ResponseCollectionStatus

    async def complete(self, request: CompleteResponseCollectionRequest) -> CompleteResponseCollectionResponse:
        """Complete response collection (stop collecting responses)"""
        try:
            async with self._response_collection_repository.context() as session:
                settings = await self._response_collection_repository.get_settings_by_vacancy(
                    session,
                    response_collection_protocol.ResponseCollectionRepositoryProtocol.GetSettingsByVacancyRequest(
                        vacancy_id=request.vacancy_id,
                    ),
                )

                if settings is None:
                    msg = (
                        f"Response collection settings not found for vacancy_id={request.vacancy_id}, "
                        "create it via InitResponseCollection first"
                    )
                    raise CompleteResponseCollectionNotFoundError(msg)

                log.info(
                    "completing response collection",
                    settings_id=settings.id,
                    vacancy_id=settings.vacancy_id,
                )

                if settings.status not in (ResponseCollectionStatus.ACTIVE, ResponseCollectionStatus.CREATED):
                    log.warning(
                        "response collection is not active or created",
                        settings_id=settings.id,
                        current_status=settings.status,
                    )
                    return self.CompleteResponseCollectionResponse(
                        vacancy_id=settings.vacancy_id,
                        status=settings.status,
                    )

                await self._response_collection_repository.update_settings_status(
                    session,
                    response_collection_protocol.ResponseCollectionRepositoryProtocol.UpdateSettingsStatusRequest(
                        settings_id=settings.id,
                        status=ResponseCollectionStatus.COMPLETED,
                    ),
                )

                log.info(
                    "response collection completed",
                    settings_id=settings.id,
                    vacancy_id=settings.vacancy_id,
                )
                return self.CompleteResponseCollectionResponse(
                    vacancy_id=settings.vacancy_id,
                    status=ResponseCollectionStatus.COMPLETED,
                )

        except CompleteResponseCollectionError:
            raise
        except Exception as e:
            log.exception("unexpected error in complete response collection", error=str(e))
            raise CompleteResponseCollectionError("unexpected error") from e
