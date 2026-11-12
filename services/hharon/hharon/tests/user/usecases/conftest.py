from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import pytest
from dishka import Provider, make_async_container
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.infra.cache import CacheConfig
from hharon.protocols import cache as cache_protocol
from hharon.protocols import user as user_protocol
from hharon.usecases.user import get_user

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.fixture
def provider(
    base_provider: Provider,
    mock_user_repository: user_protocol.HharonUserRepositoryProtocol[AsyncSession],
    mock_cache: cache_protocol.CacheProtocol,
    cache_config: CacheConfig,
) -> Provider:
    """Fixture to create dishka provider with test dependencies."""
    provider = base_provider

    _ = provider.provide(
        source=staticmethod(lambda: mock_user_repository),
        provides=user_protocol.HharonUserRepositoryProtocol[AsyncSession],
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_cache),
        provides=cache_protocol.CacheProtocol,
    )
    _ = provider.provide(
        source=staticmethod(lambda: cache_config),
        provides=CacheConfig,
    )

    # Create GetHharonUser usecase explicitly with AsyncSession
    get_user_usecase: get_user.GetHharonUser[AsyncSession] = get_user.GetHharonUser(
        user_repository=mock_user_repository,
        cache=mock_cache,
    )
    _ = provider.provide(
        source=staticmethod(lambda: get_user_usecase),
        provides=get_user.GetHharonUser[AsyncSession],
    )

    return provider


@pytest.fixture
async def container(provider: Provider) -> AsyncIterator["AsyncContainer"]:
    """Fixture to create dishka container."""
    container = make_async_container(provider)
    async with container() as request_container:
        yield request_container
    await container.close()
