from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import ANY, AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.domain.scalars import SearchCampaignID
from hharon.domain.search_campaign import SearchCampaign, SearchCampaignStatus
from hharon.pkg import hhapi
from hharon.protocols import resume_search_scan as resume_search_scan_protocol
from hharon.usecases import resume_search_scan

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.mark.asyncio
async def test_complete_raises_when_campaign_not_found(
    setup_resume_search_scan_container: "AsyncContainer",
    mock_resume_search_scan_repository: Mock,
) -> None:
    """Test that complete raises CompleteSearchCampaignExecutionError when a campaign doesn't exist."""
    usecase = await setup_resume_search_scan_container.get(
        resume_search_scan.CompleteSearchCampaignExecution[AsyncSession]
    )

    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    mock_resume_search_scan_repository.context = _context
    mock_resume_search_scan_repository.get_campaign_by_vacancy = AsyncMock(return_value=None)

    request = resume_search_scan.CompleteSearchCampaignExecution.CompleteSearchCampaignExecutionRequest(
        vacancy_id="vacancy_id"
    )

    with pytest.raises(resume_search_scan.CompleteSearchCampaignExecutionError) as exc_info:
        await usecase.complete(request)

    assert "vacancy_id=" in str(exc_info.value)
    mock_resume_search_scan_repository.get_campaign_by_vacancy.assert_awaited_once()


@pytest.mark.asyncio
async def test_resumes_existing_campaign_updates_to_complete(
    setup_resume_search_scan_container: "AsyncContainer",
    mock_resume_search_scan_repository: Mock,
) -> None:
    """Test that Stop updates existing campaign to Completed"""
    usecase = await setup_resume_search_scan_container.get(
        resume_search_scan.CompleteSearchCampaignExecution[AsyncSession]
    )

    vacancy_id = "vacancy_123"
    params = [hhapi.models.ResumesGetParameters(text="python")]
    campaign_id = SearchCampaignID()

    existing_campaign = SearchCampaign(
        id=campaign_id,
        user_id="user_1",
        vacancy_id=vacancy_id,
        search_params=params,
        status=SearchCampaignStatus.CREATED,
        active_until=datetime.now(UTC),
        daily_limit=30,
    )

    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    mock_resume_search_scan_repository.context = _context
    mock_resume_search_scan_repository.get_campaign_by_vacancy = AsyncMock(return_value=existing_campaign)
    mock_resume_search_scan_repository.update_campaign_status = AsyncMock(return_value=None)

    request = resume_search_scan.CompleteSearchCampaignExecution.CompleteSearchCampaignExecutionRequest(
        vacancy_id=vacancy_id
    )

    result = await usecase.complete(request)

    assert result.vacancy_id == vacancy_id
    mock_resume_search_scan_repository.get_campaign_by_vacancy.assert_awaited_once()
    mock_resume_search_scan_repository.update_campaign_status.assert_awaited_once_with(
        ANY,
        resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol.UpdateCampaignStatusRequest(
            campaign_id=campaign_id,
            status=SearchCampaignStatus.COMPLETED,
        ),
    )


@pytest.mark.asyncio
async def test_complete_raises_error_on_exception(
    setup_resume_search_scan_container: "AsyncContainer",
    mock_resume_search_scan_repository: Mock,
) -> None:
    """Test that complete raises CompleteSearchCampaignExecutionError on exception."""
    usecase = await setup_resume_search_scan_container.get(
        resume_search_scan.CompleteSearchCampaignExecution[AsyncSession]
    )

    async def _context() -> AsyncIterator[Mock]:
        raise ValueError("Database error")
        yield  # pyright: ignore[reportUnreachable]

    mock_resume_search_scan_repository.context = _context

    request = resume_search_scan.CompleteSearchCampaignExecution.CompleteSearchCampaignExecutionRequest(
        vacancy_id="vacancy_id"
    )

    with pytest.raises(resume_search_scan.CompleteSearchCampaignExecutionError):
        await usecase.complete(request)
