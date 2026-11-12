from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.domain.scalars import SearchCampaignID
from hharon.domain.search_campaign import SearchCampaign, SearchCampaignStatus
from hharon.pkg import hhapi
from hharon.usecases.hh_search_campaign.usecase import (
    SearchCampaignUsecase,
    SearchCampaignUsecaseError,
    SearchCampaignUsecaseNotFoundError,
)
from hharon_api.v1 import hharon_pb2


@pytest.mark.asyncio
async def test_get_search_campaign_settings_exists(
    setup_search_campaign_container,
    mock_resume_search_scan_repository: Mock,
    mock_search_campaign_mapper: Mock,
) -> None:
    """Test that get_search_campaign_settings returns proto when SearchCampaign exists."""
    usecase = await setup_search_campaign_container.get(SearchCampaignUsecase[AsyncSession])

    vacancy_id = "vacancy_123"
    campaign_id = SearchCampaignID()
    created_at = datetime.now(UTC)
    active_until = created_at + timedelta(days=16)
    search_params = [hhapi.ResumesGetParameters(text="python")]

    search_campaign = SearchCampaign(
        id=campaign_id,
        user_id="user_123",
        vacancy_id=vacancy_id,
        search_params=search_params,
        status=SearchCampaignStatus.ACTIVE,
        active_until=active_until,
        daily_limit=30,
    )

    expected_proto = hharon_pb2.SearchCampaign()
    expected_proto.user_id = "user_123"
    expected_proto.vacancy_id = vacancy_id
    expected_proto.daily_limit = 30

    mock_search_campaign_mapper.from_params = Mock(return_value=expected_proto)

    @asynccontextmanager
    async def _repo_ctx() -> AsyncIterator[Mock]:
        yield Mock()

    mock_resume_search_scan_repository.context = _repo_ctx
    mock_resume_search_scan_repository.get_campaign_by_vacancy = AsyncMock(return_value=search_campaign)

    request = usecase.GetSearchCampaignSettingsRequest(vacancy_id=vacancy_id)

    result = await usecase.get_search_campaign_settings(request)

    assert result.user_id == "user_123"
    assert result.vacancy_id == vacancy_id
    assert result.daily_limit == 30
    mock_search_campaign_mapper.from_params.assert_called_once_with(search_params)
    mock_resume_search_scan_repository.get_campaign_by_vacancy.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_search_campaign_settings_not_exists(
    setup_search_campaign_container,
    mock_resume_search_scan_repository: Mock,
) -> None:
    """Test that get_search_campaign_settings raises SearchCampaignUsecaseNotFoundError when SearchCampaign does not exist."""
    usecase = await setup_search_campaign_container.get(SearchCampaignUsecase[AsyncSession])

    vacancy_id = "vacancy_123"

    @asynccontextmanager
    async def _repo_ctx() -> AsyncIterator[Mock]:
        yield Mock()

    mock_resume_search_scan_repository.context = _repo_ctx
    mock_resume_search_scan_repository.get_campaign_by_vacancy = AsyncMock(return_value=None)

    request = usecase.GetSearchCampaignSettingsRequest(vacancy_id=vacancy_id)

    with pytest.raises(SearchCampaignUsecaseNotFoundError) as exc_info:
        await usecase.get_search_campaign_settings(request)

    assert vacancy_id in str(exc_info.value)
    mock_resume_search_scan_repository.get_campaign_by_vacancy.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_search_campaign_settings_raises_error(
    setup_search_campaign_container,
    mock_resume_search_scan_repository: Mock,
) -> None:
    """Test that get_search_campaign_settings raises SearchCampaignUsecaseError on unexpected error."""
    usecase = await setup_search_campaign_container.get(SearchCampaignUsecase[AsyncSession])

    vacancy_id = "vacancy_123"

    @asynccontextmanager
    async def _repo_ctx() -> AsyncIterator[Mock]:
        raise ValueError("Database error")
        yield  # pyright: ignore[reportUnreachable]

    mock_resume_search_scan_repository.context = _repo_ctx

    request = usecase.GetSearchCampaignSettingsRequest(vacancy_id=vacancy_id)

    with pytest.raises(SearchCampaignUsecaseError):
        await usecase.get_search_campaign_settings(request)
