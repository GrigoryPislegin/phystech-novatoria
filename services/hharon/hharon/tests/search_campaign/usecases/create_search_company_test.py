from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.domain.scalars import SearchCampaignID
from hharon.domain.search_campaign import SearchCampaign, SearchCampaignStatus
from hharon.usecases.hh_search_campaign.usecase import (
    SearchCampaignUsecase,
    SearchCampaignUsecaseActiveCampaignExistsError,
    SearchCampaignUsecaseError,
)
from hharon_api.v1 import hharon_pb2

if pytest.__version__:
    pass


@pytest.mark.asyncio
async def test_create_success(
    setup_search_campaign_container,
    mock_resume_search_scan_repository: Mock,
) -> None:
    usecase = await setup_search_campaign_container.get(SearchCampaignUsecase[AsyncSession])

    user_id = "user_123"
    vacancy_id = "vacancy_abc"

    @asynccontextmanager
    async def _repo_ctx() -> AsyncIterator[Mock]:
        yield Mock()

    mock_resume_search_scan_repository.context = _repo_ctx
    mock_resume_search_scan_repository.get_campaign_by_vacancy = AsyncMock(return_value=None)
    mock_resume_search_scan_repository.create_campaign = AsyncMock(return_value=Mock(vacancy_id=vacancy_id))

    request = hharon_pb2.SearchCampaign(
        user_id=user_id,
        vacancy_id=vacancy_id,
    )

    result = await usecase.create(request)

    assert result.vacancy_id == vacancy_id
    mock_resume_search_scan_repository.create_campaign.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_raises_when_active_campaign_exists(
    setup_search_campaign_container,
    mock_resume_search_scan_repository: Mock,
    mock_search_campaign_mapper: Mock,
) -> None:
    """Create fails when an active campaign already exists for the vacancy."""
    usecase = await setup_search_campaign_container.get(SearchCampaignUsecase[AsyncSession])

    vacancy_id = "vacancy_abc"
    campaign_from_request = SearchCampaign(
        id=SearchCampaignID(),
        user_id="user_123",
        vacancy_id=vacancy_id,
        search_params=[],
        status=SearchCampaignStatus.CREATED,
        active_until=datetime.now(UTC) + timedelta(days=1),
        daily_limit=30,
    )
    mock_search_campaign_mapper.from_proto = Mock(return_value=campaign_from_request)
    active_campaign = SearchCampaign(
        id=SearchCampaignID(),
        user_id="user_123",
        vacancy_id=vacancy_id,
        search_params=[],
        status=SearchCampaignStatus.ACTIVE,
        active_until=datetime.now(UTC) + timedelta(days=1),
        daily_limit=30,
    )

    @asynccontextmanager
    async def _repo_ctx() -> AsyncIterator[Mock]:
        yield Mock()

    mock_resume_search_scan_repository.context = _repo_ctx
    mock_resume_search_scan_repository.get_campaign_by_vacancy = AsyncMock(return_value=active_campaign)
    mock_resume_search_scan_repository.create_campaign = AsyncMock()

    request = hharon_pb2.SearchCampaign(
        user_id="user_123",
        vacancy_id=vacancy_id,
    )

    with pytest.raises(SearchCampaignUsecaseActiveCampaignExistsError) as exc_info:
        await usecase.create(request)

    assert vacancy_id in str(exc_info.value)
    mock_resume_search_scan_repository.create_campaign.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_raises_error_on_db_failure(
    setup_search_campaign_container,
    mock_resume_search_scan_repository: Mock,
) -> None:
    usecase = await setup_search_campaign_container.get(SearchCampaignUsecase[AsyncSession])

    @asynccontextmanager
    async def _repo_ctx() -> AsyncIterator[Mock]:
        raise ValueError("Database connection error")
        yield Mock()

    mock_resume_search_scan_repository.context = _repo_ctx

    request = hharon_pb2.SearchCampaign(
        user_id="user_123",
        vacancy_id="vacancy_abc",
    )

    with pytest.raises(SearchCampaignUsecaseError):
        await usecase.create(request)


@pytest.mark.asyncio
async def test_create_raises_unexpected_error(
    setup_search_campaign_container,
    mock_resume_search_scan_repository: Mock,
) -> None:
    usecase = await setup_search_campaign_container.get(SearchCampaignUsecase[AsyncSession])

    async def _repo_ctx() -> AsyncIterator[Mock]:
        raise ValueError("db error")
        yield  # pyright: ignore[reportUnreachable]

    mock_resume_search_scan_repository.context = _repo_ctx

    request = hharon_pb2.SearchCampaign(
        user_id="user_123",
        vacancy_id="vacancy_abc",
    )

    with pytest.raises(SearchCampaignUsecaseError):
        await usecase.create(request)


@pytest.mark.asyncio
async def test_create_raises_error_on_create_search_campaign_failure(
    setup_search_campaign_container,
    mock_resume_search_scan_repository: Mock,
) -> None:
    usecase = await setup_search_campaign_container.get(SearchCampaignUsecase[AsyncSession])

    @asynccontextmanager
    async def _repo_ctx() -> AsyncIterator[Mock]:
        yield Mock()

    mock_resume_search_scan_repository.context = _repo_ctx
    mock_resume_search_scan_repository.get_campaign_by_vacancy = AsyncMock(return_value=None)
    mock_resume_search_scan_repository.create_campaign = AsyncMock(side_effect=Exception("Creation failed"))

    request = hharon_pb2.SearchCampaign(
        user_id="user_123",
        vacancy_id="vacancy_abc",
    )

    with pytest.raises(SearchCampaignUsecaseError):
        await usecase.create(request)
