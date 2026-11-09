from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class Oauth2TokenQueueError(Exception): ...


class Oauth2TokenQueueProtocol(ABC):
    class UpsertTokenRequest(BaseModel):
        token_id: str
        expires_at: datetime
        zset_key: str

    @abstractmethod
    async def upsert_token(self, request: UpsertTokenRequest) -> None:
        """inserts token_id and expires_at or updates expires_at

        Raises:
            Oauth2TokenQueueError - not expected exception
        Returns:
            None
        """
        ...

    class RemoveTokenRequest(BaseModel):
        token_id: str
        zset_key: str

    @abstractmethod
    async def remove_token(self, request: RemoveTokenRequest) -> None:
        """removes token

        Raises:
            Oauth2TokenQueueError - not expected exception
        Returns:
            None
        """
        ...

    class ReadEarliestTokenRequest(BaseModel):
        zset_key: str

    class ReadEarliestTokenResponse(BaseModel):
        token_id: str
        expires_at: datetime

    @abstractmethod
    async def read_earliest_token(self, request: ReadEarliestTokenRequest) -> ReadEarliestTokenResponse | None:
        """reads the earliest token by expires_at

        Raises:
            Oauth2TokenQueueError - not expected exception
        Returns:
            ReadEarliestTokenResponse - the retrieved earliest token or None
        """
        ...
