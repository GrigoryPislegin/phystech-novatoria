from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.domain.token import TokenPair
from hharon.protocols import oauth2 as oauth2_protocol
from hharon.protocols import token as token_protocol
from hharon.usecases.crypt import cipher
from hharon.usecases.outbox_task.schedulers import token_update_scheduler
from hharon.usecases.token import refresh_tokens

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.mark.asyncio
async def test_refresh_tokens_refreshes_tokens_successfully(refresh_tokens_container: "AsyncContainer") -> None:
    """Test that refresh_tokens refreshes tokens via OAuth2 API."""
    usecase = cast(
        "refresh_tokens.RefreshTokens[AsyncSession]",
        await refresh_tokens_container.get(refresh_tokens.RefreshTokens),
    )
    assert isinstance(usecase, refresh_tokens.RefreshTokens)

    token_repository: Mock = cast(
        "Mock", await refresh_tokens_container.get(token_protocol.HeadHunterTokenRepositoryProtocol)
    )
    hh_oauth2_adapter: Mock = cast("Mock", await refresh_tokens_container.get(oauth2_protocol.OAuth2Protocol))
    cipher_usecase: cipher.CipherUsecase = await refresh_tokens_container.get(cipher.CipherUsecase)
    token_update_scheduler_mock = cast(
        "Mock",
        await refresh_tokens_container.get(token_update_scheduler.TokenUpdateScheduler[AsyncSession]),
    )

    user_id = "user123"
    old_refresh_token = "old_refresh_token"
    new_access_token = "new_access_token"
    new_refresh_token = "new_refresh_token"
    new_expires_in = 7200

    encrypt_old_refresh_response = cipher_usecase.encrypt_bytes(
        cipher.CipherUsecase.EncryptBytesRequest(data=old_refresh_token.encode("utf-8"))
    )

    expires_at = datetime.now(UTC) + timedelta(seconds=3600)
    old_token_pair = TokenPair(
        user_id=user_id,
        encrypted_access_token=b"old_encrypted_access",
        encrypted_refresh_token=encrypt_old_refresh_response.data,
        expires_at=expires_at,
        token_type="bearer",
        is_invalid=False,
    )

    # Mock OAuth2 response
    new_expires_at = datetime.now(UTC) + timedelta(seconds=new_expires_in)
    token_response = oauth2_protocol.OAuth2Protocol.TokenResponse(
        token=oauth2_protocol.Token(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_in=new_expires_in,
            expires_at=new_expires_at,
            token_type="bearer",
        )
    )

    # Mock context manager
    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    token_repository.context = _context
    token_repository.lock_tokens_for_update = AsyncMock(return_value=old_token_pair)

    def _update_tokens(
        _session: Mock, request: token_protocol.HeadHunterTokenRepositoryProtocol.UpdateTokensRequest
    ) -> TokenPair:
        return TokenPair(
            user_id=request.user_id,
            encrypted_access_token=request.encrypted_access_token,
            encrypted_refresh_token=request.encrypted_refresh_token,
            expires_at=request.expires_at,
            token_type=request.token_type,
            is_invalid=request.is_invalid or False,
        )

    token_repository.update_tokens = AsyncMock(side_effect=_update_tokens)
    hh_oauth2_adapter.refresh_tokens = AsyncMock(return_value=token_response)

    # Mock token_update_scheduler.schedule
    token_update_scheduler_mock.schedule = AsyncMock()

    resp = await usecase.refresh_tokens(refresh_tokens.RefreshTokens.RefreshTokensRequest(user_id=user_id))

    assert resp.access_token == new_access_token
    assert resp.refresh_token == new_refresh_token
    assert resp.expires_in == new_expires_in
    token_repository.lock_tokens_for_update.assert_awaited_once()  # pyright: ignore[reportAny]
    hh_oauth2_adapter.refresh_tokens.assert_awaited_once()  # pyright: ignore[reportAny]
    token_repository.update_tokens.assert_awaited_once()  # pyright: ignore[reportAny]
    token_update_scheduler_mock.schedule.assert_awaited_once()  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_refresh_tokens_raises_error_when_not_found(refresh_tokens_container: "AsyncContainer") -> None:
    """Test that refresh_tokens raises error when tokens are not found."""
    usecase = cast(
        "refresh_tokens.RefreshTokens[AsyncSession]",
        await refresh_tokens_container.get(refresh_tokens.RefreshTokens),
    )
    assert isinstance(usecase, refresh_tokens.RefreshTokens)

    token_repository = cast(
        "Mock", await refresh_tokens_container.get(token_protocol.HeadHunterTokenRepositoryProtocol)
    )

    user_id = "user123"

    # Mock context manager
    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    token_repository.context = _context
    token_repository.lock_tokens_for_update = AsyncMock(return_value=None)

    with pytest.raises(refresh_tokens.RefreshTokensNotFoundError):
        _ = await usecase.refresh_tokens(refresh_tokens.RefreshTokens.RefreshTokensRequest(user_id=user_id))


@pytest.mark.asyncio
async def test_refresh_tokens_marks_invalid_on_api_error(refresh_tokens_container: "AsyncContainer") -> None:
    """Test that refresh_tokens marks tokens as invalid on API error."""
    usecase = cast(
        "refresh_tokens.RefreshTokens[AsyncSession]",
        await refresh_tokens_container.get(refresh_tokens.RefreshTokens),
    )
    assert isinstance(usecase, refresh_tokens.RefreshTokens)

    user_id = "user123"

    token_repository = cast(
        "Mock", await refresh_tokens_container.get(token_protocol.HeadHunterTokenRepositoryProtocol)
    )
    hh_oauth2_adapter = cast("Mock", await refresh_tokens_container.get(oauth2_protocol.OAuth2Protocol))
    cipher_usecase = await refresh_tokens_container.get(cipher.CipherUsecase)

    old_refresh_token = "old_refresh_token"

    encrypt_old_refresh_response = cipher_usecase.encrypt_bytes(
        cipher.CipherUsecase.EncryptBytesRequest(data=old_refresh_token.encode("utf-8"))
    )

    expires_at = datetime.now(UTC) + timedelta(seconds=3600)
    old_token_pair = TokenPair(
        user_id=user_id,
        encrypted_access_token=b"old_encrypted_access",
        encrypted_refresh_token=encrypt_old_refresh_response.data,
        expires_at=expires_at,
        token_type="bearer",
        is_invalid=False,
    )

    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    token_repository.context = _context
    token_repository.lock_tokens_for_update = AsyncMock(return_value=old_token_pair)
    hh_oauth2_adapter.refresh_tokens = AsyncMock(side_effect=oauth2_protocol.OAuth2APIError("API error"))

    def _mark_invalid(
        _session: Mock, request: token_protocol.HeadHunterTokenRepositoryProtocol.MarkTokensInvalidRequest
    ) -> TokenPair:
        return TokenPair(
            user_id=request.user_id,
            encrypted_access_token=b"encrypted",
            encrypted_refresh_token=b"encrypted",
            expires_at=expires_at,
            token_type="bearer",
            is_invalid=True,
        )

    token_repository.mark_tokens_invalid = AsyncMock(side_effect=_mark_invalid)

    with pytest.raises(refresh_tokens.RefreshTokensAPIError):
        _ = await usecase.refresh_tokens(refresh_tokens.RefreshTokens.RefreshTokensRequest(user_id=user_id))

    token_repository.mark_tokens_invalid.assert_awaited_once()  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_refresh_tokens_raises_error_on_schedule_failure(refresh_tokens_container: "AsyncContainer") -> None:
    """Test that refresh_tokens raises error when scheduling next refresh task fails."""
    usecase = cast(
        "refresh_tokens.RefreshTokens[AsyncSession]",
        await refresh_tokens_container.get(refresh_tokens.RefreshTokens),
    )
    assert isinstance(usecase, refresh_tokens.RefreshTokens)

    token_repository: Mock = cast(
        "Mock", await refresh_tokens_container.get(token_protocol.HeadHunterTokenRepositoryProtocol)
    )
    hh_oauth2_adapter: Mock = cast("Mock", await refresh_tokens_container.get(oauth2_protocol.OAuth2Protocol))
    cipher_usecase: cipher.CipherUsecase = await refresh_tokens_container.get(cipher.CipherUsecase)
    token_update_scheduler_mock = cast(
        "Mock",
        await refresh_tokens_container.get(token_update_scheduler.TokenUpdateScheduler[AsyncSession]),
    )

    user_id = "user123"
    old_refresh_token = "old_refresh_token"
    new_access_token = "new_access_token"
    new_refresh_token = "new_refresh_token"
    new_expires_in = 7200

    encrypt_old_refresh_response = cipher_usecase.encrypt_bytes(
        cipher.CipherUsecase.EncryptBytesRequest(data=old_refresh_token.encode("utf-8"))
    )

    expires_at = datetime.now(UTC) + timedelta(seconds=3600)
    old_token_pair = TokenPair(
        user_id=user_id,
        encrypted_access_token=b"old_encrypted_access",
        encrypted_refresh_token=encrypt_old_refresh_response.data,
        expires_at=expires_at,
        token_type="bearer",
        is_invalid=False,
    )

    # Mock OAuth2 response
    new_expires_at = datetime.now(UTC) + timedelta(seconds=new_expires_in)
    token_response = oauth2_protocol.OAuth2Protocol.TokenResponse(
        token=oauth2_protocol.Token(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_in=new_expires_in,
            expires_at=new_expires_at,
            token_type="bearer",
        )
    )

    # Mock context manager
    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    token_repository.context = _context
    token_repository.lock_tokens_for_update = AsyncMock(return_value=old_token_pair)

    def _update_tokens(
        _session: Mock, request: token_protocol.HeadHunterTokenRepositoryProtocol.UpdateTokensRequest
    ) -> TokenPair:
        return TokenPair(
            user_id=request.user_id,
            encrypted_access_token=request.encrypted_access_token,
            encrypted_refresh_token=request.encrypted_refresh_token,
            expires_at=request.expires_at,
            token_type=request.token_type,
            is_invalid=request.is_invalid or False,
        )

    token_repository.update_tokens = AsyncMock(side_effect=_update_tokens)
    hh_oauth2_adapter.refresh_tokens = AsyncMock(return_value=token_response)

    # Mock token_update_scheduler.schedule to raise error
    token_update_scheduler_mock.schedule = AsyncMock(side_effect=Exception("Schedule error"))

    with pytest.raises(refresh_tokens.RefreshTokensScheduleError):
        _ = await usecase.refresh_tokens(refresh_tokens.RefreshTokens.RefreshTokensRequest(user_id=user_id))

    token_repository.lock_tokens_for_update.assert_awaited_once()  # pyright: ignore[reportAny]
    hh_oauth2_adapter.refresh_tokens.assert_awaited_once()  # pyright: ignore[reportAny]
    token_repository.update_tokens.assert_awaited_once()  # pyright: ignore[reportAny]
    token_update_scheduler_mock.schedule.assert_awaited_once()  # pyright: ignore[reportAny]
