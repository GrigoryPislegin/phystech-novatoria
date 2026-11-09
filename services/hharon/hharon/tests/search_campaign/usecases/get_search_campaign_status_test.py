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
    SearchCampaignUsecaseError,
    SearchCampaignUsecaseNotFoundError,
)


@pytest.mark.asyncio
async def test_get_search_campaign_status_exists(
    setup_search_campaign_container,
    mock_resume_search_scan_repository: Mock,
) -> None:
    """Test that get_search_campaign_status returns status when SearchCampaign exists."""
    usecase = await setup_search_campaign_container.get(SearchCampaignUsecase[AsyncSession])

    vacancy_id = "vacancy_123"
    campaign_id = SearchCampaignID()
    created_at = datetime.now(UTC)

    search_campaign = SearchCampaign(
        id=campaign_id,
        user_id="user_123",
        vacancy_id=vacancy_id,
        search_params=[],
        status=SearchCampaignStatus.ACTIVE,
        active_until=created_at + timedelta(days=16),
        daily_limit=30,
    )

    @asynccontextmanager
    async def _repo_ctx() -> AsyncIterator[Mock]:
        yield Mock()

    mock_resume_search_scan_repository.context = _repo_ctx
    mock_resume_search_scan_repository.get_campaign_by_vacancy = AsyncMock(return_value=search_campaign)
    mock_resume_search_scan_repository.count_collected_by_date = AsyncMock(collected_current=50)

    request = usecase.GetSearchCampaignStatusRequest(vacancy_id=vacancy_id)

    result = await usecase.get_search_campaign_status(request)

    assert result.status == SearchCampaignStatus.ACTIVE
    assert result.search_campaign_id == SearchCampaignID.from_uuid(campaign_id)
    assert result.user_id == "user_123"
    assert result.vacancy_id == vacancy_id

    mock_resume_search_scan_repository.get_campaign_by_vacancy.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_search_campaign_status_not_exists(
    setup_search_campaign_container,
    mock_resume_search_scan_repository: Mock,
) -> None:
    """Test that get_search_campaign_status raises SearchCampaignUsecaseNotFoundError when SearchCampaign does not exist."""
    usecase = await setup_search_campaign_container.get(SearchCampaignUsecase[AsyncSession])

    vacancy_id = "vacancy_123"

    @asynccontextmanager
    async def _repo_ctx() -> AsyncIterator[Mock]:
        yield Mock()

    mock_resume_search_scan_repository.context = _repo_ctx
    mock_resume_search_scan_repository.get_campaign_by_vacancy = AsyncMock(return_value=None)
    mock_resume_search_scan_repository.count_collected_today = AsyncMock(collected_current=0)

    request = usecase.GetSearchCampaignStatusRequest(
        vacancy_id=vacancy_id,
    )

    with pytest.raises(SearchCampaignUsecaseNotFoundError) as exc_info:
        await usecase.get_search_campaign_status(request)

    assert vacancy_id in str(exc_info.value)
    mock_resume_search_scan_repository.get_campaign_by_vacancy.assert_awaited_once()
    mock_resume_search_scan_repository.count_collected_today.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_search_campaign_status_raises_error(
    setup_search_campaign_container,
    mock_resume_search_scan_repository: Mock,
) -> None:
    """Test that get_search_campaign_status raises SearchCampaignUsecaseError on unexpected error."""
    usecase = await setup_search_campaign_container.get(SearchCampaignUsecase[AsyncSession])

    vacancy_id = "vacancy_123"

    @asynccontextmanager
    async def _repo_ctx() -> AsyncIterator[Mock]:
        raise ValueError("Database error")
        yield  # pyright: ignore[reportUnreachable]

    mock_resume_search_scan_repository.context = _repo_ctx

    request = usecase.GetSearchCampaignStatusRequest(vacancy_id=vacancy_id)

    with pytest.raises(SearchCampaignUsecaseError):
        await usecase.get_search_campaign_status(request)
