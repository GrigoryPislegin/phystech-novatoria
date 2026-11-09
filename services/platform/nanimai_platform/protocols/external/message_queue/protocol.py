from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any


class MessageQueueError(Exception):
    """Base exception for all message queue errors"""

    ...


class MessageQueueConnectionError(MessageQueueError):
    """Raised when connection to message queue fails"""

    ...


class MessageQueueTimeout(MessageQueueError):
    """Raised when timeout occurs while waiting for messages"""

    ...


class MessageQueueChannelError(MessageQueueError):
    """Raised when channel operation fails"""

    ...


class Message:
    """Represents a message from the queue"""

    def __init__(
        self,
        body: bytes,
        delivery_tag: Any,
        routing_key: str,
        exchange: str,
        headers: dict[str, Any] | None = None,
        content_type: str | None = None,
        content_encoding: str | None = None,
    ):
        self.body = body
        self.delivery_tag = delivery_tag
        self.routing_key = routing_key
        self.exchange = exchange
        self.headers = headers or {}
        self.content_type = content_type
        self.content_encoding = content_encoding
        self.aio_pika_message_ref: Any = None  # Internal reference for adapter use

    def decode(self, encoding: str = "utf-8") -> str:
        """Decode message body to string

        Args:
            encoding: Character encoding to use (default: utf-8)

        Returns:
            Decoded message body as string
        """
        return self.body.decode(encoding)

    def __repr__(self) -> str:
        return f"Message(routing_key={self.routing_key!r}, exchange={self.exchange!r}, body_size={len(self.body)})"


class MessageQueueProtocol(ABC):
    """Protocol for message queue operations"""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to message queue

        Raises:
            MessageQueueConnectionError: Failed to connect to message queue
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to message queue

        Raises:
            MessageQueueError: Error during disconnection
        """
        ...

    @abstractmethod
    async def pull(
        self,
        queue_name: str,
        *,
        prefetch_count: int = 1,
        auto_ack: bool = False,
    ) -> AsyncGenerator[Message, None]:
        """Pull messages from queue as async generator

        Args:
            queue_name: Name of the queue to pull messages from
            prefetch_count: Number of messages to prefetch (default: 1)
            auto_ack: Whether to automatically acknowledge messages (default: False)

        Yields:
            Message: Messages from the queue

        Raises:
            MessageQueueConnectionError: Not connected to message queue
            MessageQueueChannelError: Failed to create or configure channel
            MessageQueueTimeout: Timeout while waiting for messages
            MessageQueueError: Other errors during message pulling

        Example:
            ```python
            async for message in adapter.pull("my_queue"):
                try:
                    data = message.decode()
                    # Process message
                    await adapter.ack(message)
                except Exception:
                    await adapter.nack(message)
            ```
        """
        ...
        yield  # type: ignore

    @abstractmethod
    async def ack(self, message: Message) -> None:
        """Acknowledge message processing

        Args:
            message: Message to acknowledge

        Raises:
            MessageQueueChannelError: Failed to acknowledge message
        """
        ...

    @abstractmethod
    async def nack(self, message: Message, *, requeue: bool = True) -> None:
        """Negative acknowledge message (reject)

        Args:
            message: Message to reject
            requeue: Whether to requeue the message (default: True)

        Raises:
            MessageQueueChannelError: Failed to reject message
        """
        ...

    @abstractmethod
    async def reject(self, message: Message, *, requeue: bool = False) -> None:
        """Reject message

        Args:
            message: Message to reject
            requeue: Whether to requeue the message (default: False)

        Raises:
            MessageQueueChannelError: Failed to reject message
        """
        ...

    async def __aenter__(self) -> "MessageQueueProtocol":
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit"""
        await self.disconnect()
