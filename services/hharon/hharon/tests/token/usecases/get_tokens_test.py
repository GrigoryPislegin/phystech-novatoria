from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock

import pytest

from hharon.domain.token import TokenPair
from hharon.protocols import token as token_protocol
from hharon.usecases.crypt import cipher
from hharon.usecases.token import get_tokens

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.mark.asyncio
async def test_get_tokens_returns_decrypted_tokens(get_tokens_container: "AsyncContainer") -> None:
    """Test that get_tokens decrypts and returns tokens."""
    usecase = await get_tokens_container.get(get_tokens.GetTokens)
    assert isinstance(usecase, get_tokens.GetTokens)

    token_repository = cast("Mock", await get_tokens_container.get(token_protocol.HeadHunterTokenRepositoryProtocol))
    cipher_usecase = await get_tokens_container.get(cipher.CipherUsecase)

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
    token_repository.get_tokens = AsyncMock(return_value=token_pair)

    resp = await usecase.get_tokens(get_tokens.GetTokens.GetTokensRequest(user_id=user_id))

    assert resp.access_token == access_token
    assert resp.refresh_token == refresh_token
    assert resp.token_type == "bearer"
    assert resp.is_invalid is False
    token_repository.get_tokens.assert_awaited_once()  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_get_tokens_raises_error_when_not_found(get_tokens_container: "AsyncContainer") -> None:
    """Test that get_tokens raises error when tokens are not found."""
    usecase = await get_tokens_container.get(get_tokens.GetTokens)
    assert isinstance(usecase, get_tokens.GetTokens)

    token_repository = cast("Mock", await get_tokens_container.get(token_protocol.HeadHunterTokenRepositoryProtocol))

    user_id = "user1234"

    # Mock context manager
    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    token_repository.context = _context
    token_repository.get_tokens = AsyncMock(return_value=None)

    with pytest.raises(get_tokens.GetTokensNotFoundError):
        _ = await usecase.get_tokens(get_tokens.GetTokens.GetTokensRequest(user_id=user_id))


@pytest.mark.asyncio
async def test_get_tokens_raises_error_when_invalid(get_tokens_container: "AsyncContainer") -> None:
    """Test that get_tokens raises error when tokens are marked as invalid."""
    usecase = await get_tokens_container.get(get_tokens.GetTokens)
    assert isinstance(usecase, get_tokens.GetTokens)
    user_id = "user123"

    token_repository = cast("Mock", await get_tokens_container.get(token_protocol.HeadHunterTokenRepositoryProtocol))

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
    token_repository.get_tokens = AsyncMock(return_value=token_pair)

    with pytest.raises(get_tokens.GetTokensNotFoundError):
        _ = await usecase.get_tokens(get_tokens.GetTokens.GetTokensRequest(user_id=user_id))
