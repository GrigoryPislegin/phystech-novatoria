import json
from collections.abc import AsyncGenerator
from enum import StrEnum
from typing import final

import structlog
from pydantic import BaseModel

from nanimai_platform.domain.candidate.candidate import Candidate
from nanimai_platform.domain.operation.operation import (
    BaseOperation,
    Operation,
)
from nanimai_platform.domain.project.project import Project
from nanimai_platform.domain.scalar.scalars import UserID
from nanimai_platform.domain.vacancy.vacancy import Vacancy
from nanimai_platform.protocols.internal.pubsub import PubSubError, PubSubProtocol

log = structlog.stdlib.get_logger("app.service.UpdateStreamService")


class UpdateStreamServiceError(Exception): ...


class EventType(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


class EntityType(StrEnum):
    PROJECT = "project"
    VACANCY = "vacancy"
    CANDIDATE = "candidate"
    OPERATION = "operation"


type Payload = Project | Vacancy | Candidate | Operation


class UpdateEvent(BaseModel):
    user_id: UserID
    event_type: EventType
    entity_type: EntityType
    payload: Payload


@final
class UpdateStreamService:
    def __init__(self, pubsub: PubSubProtocol):
        self._pubsub = pubsub

    class PushRequest(BaseModel):
        user_id: UserID
        event_type: EventType
        entity: Payload

    async def push(self, request: PushRequest) -> None:
        """Push an entity update to the update stream

        Args:
            request: PushRequest containing event type and entity

        Raises:
            UpdateStreamServiceError: if publishing fails
        """
        try:
            entity = request.entity

            if isinstance(entity, Project):
                entity_type = EntityType.PROJECT
            elif isinstance(entity, Vacancy):
                entity_type = EntityType.VACANCY
            elif isinstance(entity, Candidate):
                entity_type = EntityType.CANDIDATE
            elif isinstance(entity, BaseOperation):  # pyright: ignore[reportUnnecessaryIsInstance]
                entity_type = EntityType.OPERATION
            else:
                return

            room = f"{request.user_id}"

            event = UpdateEvent(
                user_id=request.user_id,
                event_type=request.event_type,
                entity_type=entity_type,
                payload=entity,
            )

            message = event.model_dump_json()
            await self._pubsub.publish(room, message)

            log.debug("pushed update event", room=room, event_type=request.event_type, entity_type=entity_type)

        except PubSubError as e:
            log.error("failed to push update event", err=e)
            raise UpdateStreamServiceError(f"failed to push update event: {e}") from e
        except Exception as e:
            log.error("unexpected error while pushing update event", err=e)
            raise UpdateStreamServiceError(f"unexpected error while pushing update event: {e}") from e

    class PullRequest(BaseModel):
        user_id: UserID

    async def pull(self, request: PullRequest) -> AsyncGenerator[UpdateEvent, None]:
        """Pull all update events for a user

        Args:
            request: PullRequest containing user_id

        Yields:
            UpdateEvent: events for the user

        Raises:
            UpdateStreamServiceError: if subscription fails
        """
        try:
            # Subscribe to user room: {user_id}
            room = f"{request.user_id}"

            async for message in self._pubsub.subscribe(room):
                try:
                    event = UpdateEvent.model_validate_json(message)
                    yield event
                except json.JSONDecodeError as e:
                    log.warn("failed to decode message", err=e, message=message)
                    continue
                except Exception as e:
                    log.warn("failed to parse update event", err=e, message=message)
                    continue

        except PubSubError as e:
            log.error("failed to pull update events", err=e)
            raise UpdateStreamServiceError(f"failed to pull update events: {e}") from e
        except Exception as e:
            log.error("unexpected error while pulling update events", err=e)
            raise UpdateStreamServiceError(f"unexpected error while pulling update events: {e}") from e
