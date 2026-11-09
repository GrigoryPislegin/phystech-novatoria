from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock, patch

import pytest

from hharon.domain.token import TokenPair
from hharon.protocols import token as token_protocol
from hharon.usecases.crypt import cipher
from hharon.usecases.token import save_tokens

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.mark.asyncio
async def test_save_tokens_saves_encrypted_tokens(save_tokens_container: "AsyncContainer") -> None:
    """Test that save_tokens encrypts and saves tokens."""
    usecase = await save_tokens_container.get(save_tokens.SaveTokens)
    assert isinstance(usecase, save_tokens.SaveTokens)

    token_repository = cast("Mock", await save_tokens_container.get(token_protocol.HeadHunterTokenRepositoryProtocol))

    user_id = "user123"
    access_token = "test_access_token"
    refresh_token = "test_refresh_token"
    expires_in = 3600

    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    token_repository.context = _context

    def _save_tokens(
        _session: Mock, request: token_protocol.HeadHunterTokenRepositoryProtocol.SaveTokensRequest
    ) -> TokenPair:
        return TokenPair(
            user_id=request.user_id,
            encrypted_access_token=request.encrypted_access_token,
            encrypted_refresh_token=request.encrypted_refresh_token,
            expires_at=request.expires_at,
            token_type=request.token_type,
        )

    token_repository.save_tokens = AsyncMock(side_effect=_save_tokens)

    resp = await usecase.save_tokens(
        save_tokens.SaveTokens.SaveTokensRequest(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )
    )

    assert resp.token_pair.user_id == user_id
    assert resp.token_pair.token_type == "bearer"
    token_repository.save_tokens.assert_awaited_once()  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_save_tokens_raises_error_on_encryption_failure(save_tokens_container: "AsyncContainer") -> None:
    """Test that save_tokens raises error when encryption fails."""
    usecase = await save_tokens_container.get(save_tokens.SaveTokens)
    assert isinstance(usecase, save_tokens.SaveTokens)

    user_id = "user123"

    # Break encryption by patching encrypt_bytes method on the cipher_usecase instance
    cipher_usecase = await save_tokens_container.get(cipher.CipherUsecase)
    with patch.object(
        cipher_usecase, "encrypt_bytes", side_effect=cipher.CipherUsecaseEncryptError("encryption failed")
    ):
        with pytest.raises(save_tokens.SaveTokensEncryptError):
            _ = await usecase.save_tokens(
                save_tokens.SaveTokens.SaveTokensRequest(
                    user_id=user_id,
                    access_token="test_token",
                    refresh_token="test_refresh",
                    expires_in=3600,
                )
            )
