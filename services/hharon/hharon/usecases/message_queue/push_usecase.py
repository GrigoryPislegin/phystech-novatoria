from datetime import UTC, datetime
from typing import final
from uuid import uuid4

import structlog

from hharon.protocols.message_queue.push_protocol import (
    PushingProtocol,
    PushingProtocolError,
    PushingProtocolPublishError,
    PushingProtocolQueueConnectionError,
)

log = structlog.stdlib.get_logger("hharon.usecases.MessageQueuePushUsecase")


class MQPushUsecaseError(Exception): ...


class MQPushUsecaseQueueConnectionError(MQPushUsecaseError): ...


class MQPushUsecasePublishError(MQPushUsecaseError): ...


@final
class MessageQueuePushUsecase:
    def __init__(
        self,
        adapter: PushingProtocol,
    ):
        self._adapter = adapter

    async def push(self, queue: str, payload: bytes) -> str:
        """Push a message to the message queue.

        Args:
            queue: Name of the target queue
            payload: The bytes to send

        Returns:
            Message ID for tracking

        Raises:
            QueueConnectionError: If connection to broker fails
            PublishError: If message publishing fails
            Error: For any other unexpected errors
        """
        try:
            now = datetime.now(UTC)

            message = PushingProtocol.Message(
                id=uuid4().hex,
                timestamp=now,
                payload=payload,
            )

            await self._adapter.push(message, queue)
        except PushingProtocolQueueConnectionError as e:
            raise MQPushUsecaseQueueConnectionError from e
        except PushingProtocolPublishError as e:
            raise MQPushUsecasePublishError from e
        except PushingProtocolError as e:
            raise MQPushUsecaseError from e
        except Exception as e:
            raise MQPushUsecaseError from e
        else:
            log.info(
                "pushed message to queue",
                message_id=message.id,
                queue_name=queue,
            )

            return message.id
