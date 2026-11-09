from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest
from dishka import Provider, make_async_container
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.protocols import CacheProtocol, ResumeSearchScanHHApiProtocol
from hharon.usecases.hh_manager_access.usecase import GetHHSearchCampaignAccessUsecase
from hharon.usecases.token.get_tokens import GetTokens
from hharon.usecases.user.get_user import GetHharonUser

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.fixture
def mock_get_tokens_usecase() -> Mock:
    uc = Mock(spec=GetTokens)
    uc.get_tokens = AsyncMock()
    return uc


@pytest.fixture
def mock_get_user_usecase() -> Mock:
    uc = Mock(spec=GetHharonUser)
    uc.get_user = AsyncMock()
    return uc


@pytest.fixture
def mock_hh_api_adapter() -> Mock:
    return Mock(spec=ResumeSearchScanHHApiProtocol)


@pytest.fixture
def mock_cache() -> Mock:
    cache = Mock(spec=CacheProtocol)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


@pytest.fixture
def setup_get_manager_access_provider(
    base_provider: Provider,
    mock_get_tokens_usecase: Mock,
    mock_hh_api_adapter: Mock,
    mock_get_user_usecase: Mock,
    mock_cache: Mock,
) -> Provider:
    provider = base_provider

    _ = provider.provide(
        source=staticmethod(lambda: mock_get_tokens_usecase),
        provides=GetTokens,
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_hh_api_adapter),
        provides=ResumeSearchScanHHApiProtocol,
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_get_user_usecase),
        provides=GetHharonUser[AsyncSession],
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_cache),
        provides=CacheProtocol,
    )

    usecase = GetHHSearchCampaignAccessUsecase[AsyncSession](
        _get_tokens_usecase=mock_get_tokens_usecase,
        _get_user_usecase=mock_get_user_usecase,
        _hh_api=mock_hh_api_adapter,
        _cache=mock_cache,
    )
    _ = provider.provide(
        source=staticmethod(lambda: usecase),
        provides=GetHHSearchCampaignAccessUsecase[AsyncSession],
    )

    return provider


@pytest.fixture
async def setup_get_manager_access_container(
    setup_get_manager_access_provider: Provider,
) -> AsyncIterator["AsyncContainer"]:
    container = make_async_container(setup_get_manager_access_provider)
    async with container() as request_container:
        yield request_container
    await container.close()
