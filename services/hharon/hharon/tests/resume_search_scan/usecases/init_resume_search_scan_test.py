from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import ANY, AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.domain.outbox_task import OutboxTask, OutboxTaskStatus, OutboxTaskType
from hharon.domain.scalars import SearchCampaignID, TaskID
from hharon.domain.search_campaign import SearchCampaign, SearchCampaignStatus
from hharon.protocols import resume_search_scan as resume_search_scan_protocol
from hharon.usecases import resume_search_scan

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.mark.asyncio
async def test_init_raises_when_campaign_not_found(
    setup_resume_search_scan_container: "AsyncContainer",
    mock_resume_search_scan_repository: Mock,
) -> None:
    """Test that init raises InitSearchCampaignExecutionError when campaign doesn't exist."""
    usecase = await setup_resume_search_scan_container.get(resume_search_scan.InitSearchCampaignExecution[AsyncSession])

    vacancy_id = "vacancy_id"

    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    mock_resume_search_scan_repository.context = _context
    mock_resume_search_scan_repository.get_campaign_by_vacancy = AsyncMock(return_value=None)

    request = resume_search_scan.InitSearchCampaignExecution.InitSearchCampaignExecutionRequest(vacancy_id=vacancy_id)

    with pytest.raises(resume_search_scan.InitSearchCampaignExecutionError) as exc_info:
        await usecase.init(request)

    assert str(vacancy_id) in str(exc_info.value)
    mock_resume_search_scan_repository.get_campaign_by_vacancy.assert_awaited_once()


@pytest.mark.asyncio
async def test_init_resumes_existing_campaign_sets_active_and_schedules_task(
    setup_resume_search_scan_container: "AsyncContainer",
    mock_resume_search_scan_repository: Mock,
    mock_outbox_repository: Mock,
) -> None:
    """Test that init updates existing campaign to ACTIVE and schedules task (e.g. after CreateSearchCampaign)."""
    usecase = await setup_resume_search_scan_container.get(resume_search_scan.InitSearchCampaignExecution[AsyncSession])

    vacancy_id = "vacancy_123"
    campaign_id = SearchCampaignID()
    task_id = TaskID()

    existing_campaign = SearchCampaign(
        id=campaign_id,
        user_id="user_1",
        vacancy_id=vacancy_id,
        search_params=[],
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

    mock_task = OutboxTask(
        id=task_id,
        task_type=OutboxTaskType.RESUME_SEARCH_SCAN,
        payload={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        available_at=datetime.now(UTC),
        attempts=0,
        status=OutboxTaskStatus.PENDING,
    )
    mock_outbox_repository.create_task = AsyncMock(return_value=mock_task)

    request = resume_search_scan.InitSearchCampaignExecution.InitSearchCampaignExecutionRequest(
        vacancy_id="vacancy_id",
    )

    result = await usecase.init(request)

    assert result.vacancy_id == existing_campaign.vacancy_id
    mock_resume_search_scan_repository.get_campaign_by_vacancy.assert_awaited_once()
    mock_resume_search_scan_repository.update_campaign_status.assert_awaited_once_with(
        ANY,
        resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol.UpdateCampaignStatusRequest(
            campaign_id=campaign_id,
            status=SearchCampaignStatus.ACTIVE,
        ),
    )
    mock_outbox_repository.create_task.assert_awaited_once()


@pytest.mark.asyncio
async def test_init_raises_error_on_exception(
    setup_resume_search_scan_container: "AsyncContainer",
    mock_resume_search_scan_repository: Mock,
) -> None:
    """Test that init raises InitSearchCampaignExecutionError on exception."""
    usecase = await setup_resume_search_scan_container.get(resume_search_scan.InitSearchCampaignExecution[AsyncSession])

    async def _context() -> AsyncIterator[Mock]:
        raise ValueError("Database error")
        yield  # pyright: ignore[reportUnreachable]

    mock_resume_search_scan_repository.context = _context

    request = resume_search_scan.InitSearchCampaignExecution.InitSearchCampaignExecutionRequest(vacancy_id="vacancyid")

    with pytest.raises(resume_search_scan.InitSearchCampaignExecutionError):
        await usecase.init(request)
