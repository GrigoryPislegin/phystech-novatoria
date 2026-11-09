from abc import ABC, abstractmethod


class NotificationError(Exception): ...


class NotificationTimeout(NotificationError): ...


class NotificationReceiverUnreachable(NotificationError): ...


class NotificationProtocol(ABC):
    @abstractmethod
    async def push(self, message: str) -> None:
        """Pushes message to notification channel

        Args:
            message (str): a message to send

        Raises:
            - NotificationError: Base exception for all notification errors
            - NotificationTimeout: Timeout occurred while waiting for notification
            - NotificationReceiverUnreachable: Notification receiver is unreachable
        """
        ...
