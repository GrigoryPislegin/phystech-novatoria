from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock

import pytest

from hharon.domain.token import TokenPair
from hharon.protocols import token as token_protocol
from hharon.usecases.crypt import cipher
from hharon.usecases.token import obtain_access_token

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.mark.asyncio
async def test_obtain_access_token_returns_access_token(obtain_access_token_container: "AsyncContainer") -> None:
    """Test that obtain_access_token returns decrypted access token."""
    usecase = await obtain_access_token_container.get(obtain_access_token.ObtainAccessToken)
    assert isinstance(usecase, obtain_access_token.ObtainAccessToken)

    token_repository = cast(
        "Mock", await obtain_access_token_container.get(token_protocol.HeadHunterTokenRepositoryProtocol)
    )
    cipher_usecase = await obtain_access_token_container.get(cipher.CipherUsecase)

    user_id = "user123"

    access_token = "test_access_token"
    refresh_token = "test_refresh_token"
    expires_in = 3600

    # Encrypt tokens
    encrypt_access_response = cipher_usecase.encrypt_bytes(
        cipher.CipherUsecase.EncryptBytesRequest(data=access_token.encode("utf-8"))
    )
    encrypt_refresh_response = cipher_usecase.encrypt_bytes(
        cipher.CipherUsecase.EncryptBytesRequest(data=refresh_token.encode("utf-8"))
    )

    # Create token pair with encrypted tokens
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    token_pair = TokenPair(
        user_id=user_id,
        encrypted_access_token=encrypt_access_response.data,
        encrypted_refresh_token=encrypt_refresh_response.data,
        expires_at=expires_at,
        token_type="bearer",
        is_invalid=False,
    )

    # Mock context manager
    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    token_repository.context = _context
    token_repository.lock_tokens_for_update = AsyncMock(return_value=token_pair)

    resp = await usecase.obtain_access_token(
        obtain_access_token.ObtainAccessToken.ObtainAccessTokenRequest(user_id=user_id)
    )

    assert resp.access_token == access_token
    token_repository.lock_tokens_for_update.assert_awaited_once()  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_obtain_access_token_raises_error_when_not_found(
    obtain_access_token_container: "AsyncContainer",
) -> None:
    """Test that obtain_access_token raises error when tokens are not found."""
    usecase = await obtain_access_token_container.get(obtain_access_token.ObtainAccessToken)
    assert isinstance(usecase, obtain_access_token.ObtainAccessToken)

    token_repository = cast(
        "Mock", await obtain_access_token_container.get(token_protocol.HeadHunterTokenRepositoryProtocol)
    )

    user_id = "user123"

    # Mock context manager
    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    token_repository.context = _context
    token_repository.lock_tokens_for_update = AsyncMock(return_value=None)

    with pytest.raises(obtain_access_token.ObtainAccessTokenNotFoundError):
        _ = await usecase.obtain_access_token(
            obtain_access_token.ObtainAccessToken.ObtainAccessTokenRequest(user_id=user_id)
        )


@pytest.mark.asyncio
async def test_obtain_access_token_raises_error_when_invalid(
    obtain_access_token_container: "AsyncContainer",
) -> None:
    """Test that obtain_access_token raises error when tokens are marked as invalid."""
    usecase = await obtain_access_token_container.get(obtain_access_token.ObtainAccessToken)
    assert isinstance(usecase, obtain_access_token.ObtainAccessToken)

    token_repository = cast(
        "Mock", await obtain_access_token_container.get(token_protocol.HeadHunterTokenRepositoryProtocol)
    )

    user_id = "user123"
    expires_at = datetime.now(UTC) + timedelta(seconds=3600)
    token_pair = TokenPair(
        user_id=user_id,
        encrypted_access_token=b"encrypted",
        encrypted_refresh_token=b"encrypted",
        expires_at=expires_at,
        token_type="bearer",
        is_invalid=True,
    )

    # Mock context manager
    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    token_repository.context = _context
    token_repository.lock_tokens_for_update = AsyncMock(return_value=token_pair)

    with pytest.raises(obtain_access_token.ObtainAccessTokenInvalidError):
        _ = await usecase.obtain_access_token(
            obtain_access_token.ObtainAccessToken.ObtainAccessTokenRequest(user_id=user_id)
        )


@pytest.mark.asyncio
async def test_obtain_access_token_waits_for_lock_release(
    obtain_access_token_container: "AsyncContainer",
) -> None:
    """Test that obtain_access_token waits for lock release if tokens are being refreshed."""
    usecase = await obtain_access_token_container.get(obtain_access_token.ObtainAccessToken)
    assert isinstance(usecase, obtain_access_token.ObtainAccessToken)

    token_repository = cast(
        "Mock", await obtain_access_token_container.get(token_protocol.HeadHunterTokenRepositoryProtocol)
    )
    cipher_usecase = await obtain_access_token_container.get(cipher.CipherUsecase)

    user_id = "user123"
    access_token = "test_access_token"
    refresh_token = "test_refresh_token"
    expires_in = 3600

    # Encrypt tokens
    encrypt_access_response = cipher_usecase.encrypt_bytes(
        cipher.CipherUsecase.EncryptBytesRequest(data=access_token.encode("utf-8"))
    )
    encrypt_refresh_response = cipher_usecase.encrypt_bytes(
        cipher.CipherUsecase.EncryptBytesRequest(data=refresh_token.encode("utf-8"))
    )

    # Create token pair with encrypted tokens
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    token_pair = TokenPair(
        user_id=user_id,
        encrypted_access_token=encrypt_access_response.data,
        encrypted_refresh_token=encrypt_refresh_response.data,
        expires_at=expires_at,
        token_type="bearer",
        is_invalid=False,
    )

    # Mock context manager
    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    token_repository.context = _context
    # lock_tokens_for_update will wait for lock release (in real scenario)
    token_repository.lock_tokens_for_update = AsyncMock(return_value=token_pair)

    resp = await usecase.obtain_access_token(
        obtain_access_token.ObtainAccessToken.ObtainAccessTokenRequest(user_id=user_id)
    )

    assert resp.access_token == access_token
    # Verify that lock_tokens_for_update was called (which waits for lock)
    token_repository.lock_tokens_for_update.assert_awaited_once()  # pyright: ignore[reportAny]
