from __future__ import annotations

from abc import ABC, abstractmethod

from nanimai_platform.protocols.external.message_queue import Message


class MessageHandlerError(Exception): ...


class MessageHandlerInvalidDataError(MessageHandlerError): ...


class MessageHandler(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def queue_name(self) -> str: ...

    @property
    def prefetch_count(self) -> int:
        return 1

    @abstractmethod
    async def handle(self, message: Message) -> None: ...
