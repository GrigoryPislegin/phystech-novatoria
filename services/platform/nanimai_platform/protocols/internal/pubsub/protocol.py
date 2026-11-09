from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator


class PubSubError(Exception): ...


class PubSubProtocol(ABC):
    @abstractmethod
    async def publish(self, room: str, message: str) -> None:
        """publishes message to room

        Args:
            room: room name to publish to
            message: message to publish

        Raises:
            PubSubError - not expected exception
        Returns:
            None
        """
        ...

    @abstractmethod
    def subscribe(self, room: str) -> AsyncGenerator[str, None]:
        """subscribes to room and yields messages

        Args:
            room: room name to subscribe to

        Raises:
            PubSubError - not expected exception
        Yields:
            str - messages from room
        """
        ...
