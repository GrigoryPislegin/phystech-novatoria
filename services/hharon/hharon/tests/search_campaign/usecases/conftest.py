from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest
from dishka import Provider, make_async_container
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.protocols.cache.protocol import CacheProtocol
from hharon.protocols.resume_search_scan.protocol import ResumeSearchScanRepositoryProtocol
from hharon.usecases.hh_search_campaign.mapper import SearchCampaignMapperUsecase
from hharon.usecases.hh_search_campaign.usecase import SearchCampaignUsecase
from hharon.usecases.token.get_tokens import GetTokens

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.fixture
def mock_resume_search_scan_repository() -> Mock:
    repo = Mock(spec=ResumeSearchScanRepositoryProtocol[AsyncSession])
    repo.context = AsyncMock()
    return repo


@pytest.fixture
def mock_get_tokens_usecase() -> Mock:
    uc = Mock(spec=GetTokens)
    uc.get_tokens = AsyncMock()
    return uc


@pytest.fixture
def mock_cache() -> Mock:
    cache = Mock(spec=CacheProtocol)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


@pytest.fixture
def mock_search_campaign_mapper() -> Mock:
    return Mock(spec=SearchCampaignMapperUsecase)


@pytest.fixture
def setup_search_campaign_provider(
    base_provider: Provider,
    mock_resume_search_scan_repository: Mock,
    mock_get_tokens_usecase: Mock,
    mock_search_campaign_mapper: Mock,
    mock_cache: Mock,
) -> Provider:
    provider = base_provider

    _ = provider.provide(
        source=staticmethod(lambda: mock_resume_search_scan_repository),
        provides=ResumeSearchScanRepositoryProtocol[AsyncSession],
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_get_tokens_usecase),
        provides=GetTokens,
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_search_campaign_mapper),
        provides=SearchCampaignMapperUsecase,
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_cache),
        provides=CacheProtocol,
    )

    usecase = SearchCampaignUsecase[AsyncSession](
        resume_search_scan_repository=mock_resume_search_scan_repository,
        get_tokens_usecase=mock_get_tokens_usecase,  # type: ignore[arg-type]
        mapper=mock_search_campaign_mapper,
    )
    _ = provider.provide(
        source=staticmethod(lambda: usecase),
        provides=SearchCampaignUsecase[AsyncSession],
    )

    return provider


@pytest.fixture
async def setup_search_campaign_container(
    setup_search_campaign_provider: Provider,
) -> AsyncIterator["AsyncContainer"]:
    container = make_async_container(setup_search_campaign_provider)
    async with container() as request_container:
        yield request_container
    await container.close()
