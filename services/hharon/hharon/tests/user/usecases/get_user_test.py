from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.domain.user import HharonUser
from hharon.protocols import cache as cache_protocol
from hharon.protocols import user as user_protocol
from hharon.usecases.user import get_user

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.mark.asyncio
async def test_get_user_returns_user_from_repository(container: "AsyncContainer") -> None:
    """Test that get_user returns user from repository."""
    usecase = await container.get(get_user.GetHharonUser[AsyncSession])

    user_repository = cast("Mock", await container.get(user_protocol.HharonUserRepositoryProtocol[AsyncSession]))
    cache = cast("Mock", await container.get(cache_protocol.CacheProtocol))

    user_id = "user_123"
    user = HharonUser(
        user_id=user_id,
        hh_manager_id="hh_123",
        hh_employer_id="employer_123",
        name="John Doe",
        email="john@example.com",
    )

    # Mock context manager
    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    user_repository.context = _context
    user_repository.get_user = AsyncMock(return_value=user)
    cache.get = AsyncMock(return_value=None)  # Cache miss
    cache.set = AsyncMock()

    resp = await usecase.get_user(get_user.GetHharonUser.GetHharonUserRequest(user_id=user_id))

    assert resp.user == user
    user_repository.get_user.assert_awaited_once()  # pyright: ignore[reportAny]
    cache.get.assert_awaited_once()  # pyright: ignore[reportAny]
    cache.set.assert_awaited_once()  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_get_user_raises_error_when_user_not_found(container: "AsyncContainer") -> None:
    """Test that get_user raises error when user is not found."""
    usecase = await container.get(get_user.GetHharonUser[AsyncSession])

    user_repository = cast("Mock", await container.get(user_protocol.HharonUserRepositoryProtocol[AsyncSession]))
    cache = cast("Mock", await container.get(cache_protocol.CacheProtocol))

    user_id = "user1123"

    # Mock context manager
    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    user_repository.context = _context
    user_repository.get_user = AsyncMock(return_value=None)
    cache.get = AsyncMock(return_value=None)  # Cache miss

    with pytest.raises(get_user.GetHharonUserNotFoundError):
        _ = await usecase.get_user(get_user.GetHharonUser.GetHharonUserRequest(user_id=user_id))
