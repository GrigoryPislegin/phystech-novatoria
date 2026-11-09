from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock

import pytest

from hharon.domain.token import TokenPair
from hharon.protocols import token as token_protocol
from hharon.usecases.token import mark_tokens_invalid

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.mark.asyncio
async def test_mark_tokens_invalid_marks_tokens_as_invalid(mark_tokens_invalid_container: "AsyncContainer") -> None:
    """Test that mark_tokens_invalid marks tokens as invalid."""
    usecase = await mark_tokens_invalid_container.get(mark_tokens_invalid.MarkTokensInvalid)
    assert isinstance(usecase, mark_tokens_invalid.MarkTokensInvalid)

    token_repository = cast(
        "Mock", await mark_tokens_invalid_container.get(token_protocol.HeadHunterTokenRepositoryProtocol)
    )

    user_id = "user123"
    expires_at = datetime.now(UTC) + timedelta(seconds=3600)

    # Mock context manager
    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    token_repository.context = _context

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

    resp = await usecase.mark_tokens_invalid(
        mark_tokens_invalid.MarkTokensInvalid.MarkTokensInvalidRequest(user_id=user_id)
    )

    assert resp.success is True
    token_repository.mark_tokens_invalid.assert_awaited_once()  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_mark_tokens_invalid_raises_error_when_not_found(mark_tokens_invalid_container: "AsyncContainer") -> None:
    """Test that mark_tokens_invalid raises error when tokens are not found."""
    usecase = await mark_tokens_invalid_container.get(mark_tokens_invalid.MarkTokensInvalid)
    assert isinstance(usecase, mark_tokens_invalid.MarkTokensInvalid)

    token_repository = cast(
        "Mock", await mark_tokens_invalid_container.get(token_protocol.HeadHunterTokenRepositoryProtocol)
    )

    user_id = "user123"

    # Mock context manager
    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    token_repository.context = _context
    token_repository.mark_tokens_invalid = AsyncMock(
        side_effect=token_protocol.HeadHunterTokenRepositoryNotFoundError("not found")
    )

    with pytest.raises(mark_tokens_invalid.MarkTokensInvalidNotFoundError):
        _ = await usecase.mark_tokens_invalid(
            mark_tokens_invalid.MarkTokensInvalid.MarkTokensInvalidRequest(user_id=user_id)
        )
