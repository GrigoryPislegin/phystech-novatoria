from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from hharon.domain.token import TokenPair


class HeadHunterTokenRepositoryError(Exception):
    """Base exception for HeadHunter token repository errors."""


class HeadHunterTokenRepositoryNotFoundError(HeadHunterTokenRepositoryError):
    """Token pair not found error."""


class HeadHunterTokenRepositoryProtocol[SessionT](Protocol):
    @asynccontextmanager
    async def context(self) -> AsyncGenerator[SessionT]:
        raise NotImplementedError("HeadHunterTokenRepositoryProtocol.context")
        yield  # pyright: ignore[reportUnreachable]

    @dataclass
    class SaveTokensRequest:
        """Request to save a new token pair."""

        user_id: str
        encrypted_access_token: bytes
        encrypted_refresh_token: bytes
        expires_at: datetime
        token_type: str

    async def save_tokens(self, session: SessionT, request: SaveTokensRequest) -> TokenPair: ...

    @dataclass
    class GetTokensRequest:
        """Request to get tokens by user_id."""

        user_id: str

    async def get_tokens(self, session: SessionT, request: GetTokensRequest) -> TokenPair | None: ...

    @dataclass
    class LockTokensRequest:
        """Request to lock tokens for update (SELECT FOR UPDATE)."""

        user_id: str

    async def lock_tokens_for_update(self, session: SessionT, request: LockTokensRequest) -> TokenPair | None: ...

    @dataclass
    class UpdateTokensRequest:
        """Request to update existing tokens."""

        user_id: str
        encrypted_access_token: bytes
        encrypted_refresh_token: bytes
        expires_at: datetime
        token_type: str
        is_invalid: bool | None = None

    async def update_tokens(self, session: SessionT, request: UpdateTokensRequest) -> TokenPair: ...

    @dataclass
    class MarkTokensInvalidRequest:
        """Request to mark tokens as invalid."""

        user_id: str

    async def mark_tokens_invalid(self, session: SessionT, request: MarkTokensInvalidRequest) -> TokenPair: ...
