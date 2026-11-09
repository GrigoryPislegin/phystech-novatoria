from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class PushingProtocolError(Exception): ...


class PushingProtocolQueueConnectionError(PushingProtocolError): ...


class PushingProtocolPublishError(PushingProtocolError): ...


class PushingProtocol(Protocol):
    @dataclass
    class Message:
        """Message to be pushed to the queue."""

        id: str
        timestamp: datetime
        payload: bytes

    async def push(self, message: Message, queue_name: str) -> None:
        """Push a message to the queue.

        Args:
            message: Message to push
            queue_name: name of the target queue

        Raises:
            PushingProtocolQueueConnectionError: If connection to broker fails
            PushingProtocolPublishError: If message publishing fails
            PushingProtocolError: For any other unexpected errors
        """
        ...
