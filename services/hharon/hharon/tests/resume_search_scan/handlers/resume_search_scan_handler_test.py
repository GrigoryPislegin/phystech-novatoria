from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from unittest.mock import ANY, AsyncMock, MagicMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.adapters.resume_search_scan import HeadHunterResumeSearchScanAdapter
from hharon.domain.outbox_task import OutboxTask, OutboxTaskStatus, ResumeSearchScanPayload
from hharon.domain.scalars import SearchCampaignID
from hharon.domain.search_campaign import SearchCampaign, SearchCampaignStatus
from hharon.pkg import hhapi
from hharon.pkg.hhapi.models import ResumeResumeForEmployer, ResumesSearchForResumesItem
from hharon.protocols import OutboxTaskRepositoryProtocol
from hharon.protocols import resume_search_scan as resume_search_scan_protocol
from hharon.protocols.resume_search_scan.protocol import (
    HeadHunterAccessDeniedError,
    HeadHunterRateLimitError,
)
from hharon.usecases.outbox_task.handlers import resume_search_scan_handler
from hharon.usecases.outbox_task.usecase import OutboxContext
from hharon.usecases.token import get_tokens

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.mark.asyncio
async def test_handle_raises_error_when_campaign_not_found(
    resume_search_scan_handler_container: "AsyncContainer",
    mock_resume_search_scan_repository: Mock,
    mock_resume_search_scan_task: OutboxTask,
) -> None:
    """Test that handle raises error when campaign not found."""
    handler = await resume_search_scan_handler_container.get(
        resume_search_scan_handler.ResumeSearchScanHandler[AsyncSession]
    )

    mock_session = cast("AsyncSession", Mock())
    ctx = OutboxContext(session=mock_session)

    mock_resume_search_scan_repository.get_campaign = AsyncMock(return_value=None)

    with pytest.raises(resume_search_scan_handler.ResumeSearchScanHandlerNotFoundError):
        await handler.handle(ctx=ctx, task=mock_resume_search_scan_task)


@pytest.mark.asyncio
async def test_handle_processes_resumes_successfully(
    resume_search_scan_handler_container: "AsyncContainer",
    mock_resume_search_scan_repository: Mock,
    mock_resume_search_scan_task: OutboxTask,
) -> None:
    """Test that handle processes resumes from search successfully."""
    handler = await resume_search_scan_handler_container.get(
        resume_search_scan_handler.ResumeSearchScanHandler[AsyncSession]
    )

    campaign_id = SearchCampaignID()
    campaign = SearchCampaign(
        id=campaign_id,
        user_id="user_1",
        vacancy_id="vacancy_123",
        status=SearchCampaignStatus.ACTIVE,
        active_until=datetime.now(UTC) + timedelta(days=1),
        daily_limit=100,
        search_params=[],
    )

    # Mock ResumesSearchForResumesItem (RootModel with .root.id)
    search_item = Mock(spec=ResumesSearchForResumesItem)
    search_item.root = Mock()
    search_item.root.id = "resume_789"

    mock_session = cast("AsyncSession", Mock())
    ctx = OutboxContext(session=mock_session)

    mock_resume_search_scan_repository.get_campaign = AsyncMock(return_value=campaign)
    mock_resume_search_scan_repository.mark_candidate_processed = AsyncMock(
        return_value=Mock(resume_id="resume_789", vacancy_id="vacancy_123")
    )

    @asynccontextmanager
    async def _repo_context() -> AsyncIterator[Mock]:
        yield mock_session  # pyright: ignore[reportReturnType]

    mock_resume_search_scan_repository.context = _repo_context

    get_tokens_usecase = await resume_search_scan_handler_container.get(get_tokens.GetTokens)
    mock_get_tokens_usecase = cast("Mock", get_tokens_usecase)
    mock_get_tokens_usecase.get_tokens = AsyncMock(
        return_value=get_tokens.GetTokens.GetTokensResponse(
            access_token="access_token",
            refresh_token="refresh_token",
            expires_at=datetime.now(UTC),
            token_type="bearer",
            is_invalid=False,
        )
    )

    hh_adapter = Mock(spec=HeadHunterResumeSearchScanAdapter)

    async def _get_resumes(access_token: str, params: list[hhapi.ResumesGetParameters]) -> AsyncIterator[Mock]:  # noqa: ARG001
        yield search_item

    hh_adapter.get_resumes_from_search = _get_resumes

    # Create a properly configured mock resume with all required attributes
    mock_resume = MagicMock(spec=ResumeResumeForEmployer)
    mock_resume.first_name = "John"
    mock_resume.last_name = "Doe"
    mock_resume.middle_name = None
    mock_resume.area = None
    mock_resume.gender = None
    mock_resume.age = 30
    mock_resume.title = "Software Engineer"
    mock_resume.total_experience = None
    mock_resume.experience = []
    mock_resume.skill_set = []
    mock_resume.skills = None
    mock_resume.driver_license_types = []
    mock_resume.education = MagicMock()
    mock_resume.education.level = None
    mock_resume.education.primary = []
    mock_resume.education.elementary = []
    mock_resume.education.additional = []
    mock_resume.education.attestation = []
    mock_resume.language = []
    mock_resume.contact = []
    mock_resume.salary = None
    mock_resume.alternate_url = "https://hh.ru/resume/123"
    mock_resume.model_dump_json = Mock(return_value='{"id": "resume_789"}')

    hh_adapter.get_resume = AsyncMock(return_value=mock_resume)

    handler._hh_client = hh_adapter
    handler_outbox_usecase = cast("Mock", handler._outbox_usecase)
    handler_outbox_usecase.schedule_task = AsyncMock(return_value=mock_resume_search_scan_task)

    await handler.handle(ctx=ctx, task=mock_resume_search_scan_task)

    mock_resume_search_scan_repository.get_campaign.assert_awaited_once()
    mock_resume_search_scan_repository.mark_candidate_processed.assert_awaited_once()
    handler_outbox_usecase.schedule_task.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_handles_rate_limit_error(
    resume_search_scan_handler_container: "AsyncContainer",
    mock_resume_search_scan_repository: Mock,
    mock_resume_search_scan_task: OutboxTask,
) -> None:
    """Test that handle reschedules task on rate limit error."""
    handler = await resume_search_scan_handler_container.get(
        resume_search_scan_handler.ResumeSearchScanHandler[AsyncSession]
    )

    campaign_id = SearchCampaignID()
    campaign = SearchCampaign(
        id=campaign_id,
        user_id="user_1",
        vacancy_id="vacancy_123",
        status=SearchCampaignStatus.ACTIVE,
        active_until=datetime.now(UTC) + timedelta(days=1),
        daily_limit=100,
        search_params=[],
    )

    mock_session = cast("AsyncSession", Mock())

    mock_resume_search_scan_repository.get_campaign = AsyncMock(return_value=campaign)

    get_tokens_usecase = await resume_search_scan_handler_container.get(get_tokens.GetTokens)
    mock_get_tokens_usecase = cast("Mock", get_tokens_usecase)
    mock_get_tokens_usecase.get_tokens = AsyncMock(
        return_value=get_tokens.GetTokens.GetTokensResponse(
            access_token="access_token",
            refresh_token="refresh_token",
            expires_at=datetime.now(UTC),
            token_type="bearer",
            is_invalid=False,
        )
    )

    hh_adapter = Mock(spec=HeadHunterResumeSearchScanAdapter)

    async def _get_resumes(access_token: str, params: list[hhapi.ResumesGetParameters]) -> AsyncIterator[Mock]:  # noqa: ARG001
        raise HeadHunterRateLimitError("Rate limit", retry_after=60)
        yield

    hh_adapter.get_resumes_from_search = _get_resumes
    handler._hh_client = hh_adapter

    @asynccontextmanager
    async def _outbox_context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    handler_outbox_repo = cast("Mock", handler._outbox_repo)
    handler_outbox_repo.context = _outbox_context
    handler_outbox_repo.update_task = AsyncMock(return_value=mock_resume_search_scan_task)

    with pytest.raises(HeadHunterRateLimitError):
        await handler.handle(ctx=OutboxContext(session=mock_session), task=mock_resume_search_scan_task)

    handler_outbox_repo.update_task.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_fails_task_and_campaign_on_access_denied_error(
    resume_search_scan_handler_container: "AsyncContainer",
    mock_resume_search_scan_repository: Mock,
    mock_resume_search_scan_task: OutboxTask,
) -> None:
    """Test that handle fails task and campaign on access denied error."""
    handler = await resume_search_scan_handler_container.get(
        resume_search_scan_handler.ResumeSearchScanHandler[AsyncSession]
    )

    campaign_id = SearchCampaignID()
    campaign = SearchCampaign(
        id=campaign_id,
        user_id="user_1",
        vacancy_id="vacancy_123",
        status=SearchCampaignStatus.ACTIVE,
        active_until=datetime.now(UTC) + timedelta(days=1),
        daily_limit=100,
        search_params=[],
    )

    mock_session = cast("AsyncSession", Mock())

    mock_resume_search_scan_repository.get_campaign = AsyncMock(return_value=campaign)
    mock_resume_search_scan_repository.update_campaign_status = AsyncMock(return_value=None)

    get_tokens_usecase = await resume_search_scan_handler_container.get(get_tokens.GetTokens)
    mock_get_tokens_usecase = cast("Mock", get_tokens_usecase)
    mock_get_tokens_usecase.get_tokens = AsyncMock(
        return_value=get_tokens.GetTokens.GetTokensResponse(
            access_token="access_token",
            refresh_token="refresh_token",
            expires_at=datetime.now(UTC),
            token_type="bearer",
            is_invalid=False,
        )
    )

    hh_adapter = Mock(spec=HeadHunterResumeSearchScanAdapter)

    async def _get_resumes(access_token: str, params: list[hhapi.ResumesGetParameters]) -> AsyncIterator[Mock]:  # noqa: ARG001
        raise HeadHunterAccessDeniedError("Access denied")
        yield

    hh_adapter.get_resumes_from_search = _get_resumes
    handler._hh_client = hh_adapter

    @asynccontextmanager
    async def _outbox_context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    handler_outbox_repo = cast("Mock", handler._outbox_repo)
    handler_outbox_repo.context = _outbox_context
    handler_outbox_repo.update_task = AsyncMock(return_value=mock_resume_search_scan_task)

    @asynccontextmanager
    async def _repo_context() -> AsyncIterator[Mock]:
        yield mock_session

    handler_resume_search_repo = cast("Mock", handler._resume_search_scan_repository)
    handler_resume_search_repo.context = _repo_context

    with pytest.raises(resume_search_scan_handler.ResumeSearchScanHandlerAccessDeniedError):
        await handler.handle(ctx=OutboxContext(session=mock_session), task=mock_resume_search_scan_task)

    # Verify task was marked as failed
    handler_outbox_repo.update_task.assert_awaited_once()
    await_args = handler_outbox_repo.update_task.await_args
    assert await_args is not None
    task_request = await_args.args[1]
    assert task_request.status == OutboxTaskStatus.FAILED

    # Verify campaign was marked as failed
    mock_resume_search_scan_repository.update_campaign_status.assert_awaited_once()
    campaign_update_args = mock_resume_search_scan_repository.update_campaign_status.await_args
    assert campaign_update_args is not None
    campaign_request = campaign_update_args.args[1]
    assert campaign_request.campaign_id == campaign_id
    assert campaign_request.status == SearchCampaignStatus.FAILED


@pytest.mark.asyncio
async def test_handle_completes_campaign_when_deadline_reached(
    resume_search_scan_handler_container: "AsyncContainer",
    mock_resume_search_scan_repository: Mock,
    mock_resume_search_scan_task: OutboxTask,
) -> None:
    """Test that handle completes campaign and succeeds task when deadline is reached."""
    handler = await resume_search_scan_handler_container.get(
        resume_search_scan_handler.ResumeSearchScanHandler[AsyncSession]
    )

    campaign_id = SearchCampaignID()
    campaign = SearchCampaign(
        id=campaign_id,
        user_id="user_1",
        vacancy_id="vacancy_123",
        status=SearchCampaignStatus.ACTIVE,
        active_until=datetime.now(UTC) - timedelta(days=1),  # Deadline reached
        daily_limit=100,
        search_params=[],
    )

    mock_session = cast("AsyncSession", Mock())
    ctx = OutboxContext(session=mock_session)

    mock_resume_search_scan_repository.get_campaign = AsyncMock(return_value=campaign)

    @asynccontextmanager
    async def _outbox_context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    handler_outbox_repo = cast("Mock", handler._outbox_repo)
    handler_outbox_repo.context = _outbox_context
    handler_outbox_repo.update_task = AsyncMock(return_value=mock_resume_search_scan_task)

    mock_resume_search_scan_repository.update_campaign_status = AsyncMock()

    await handler.handle(ctx=ctx, task=mock_resume_search_scan_task)

    mock_resume_search_scan_repository.update_campaign_status.assert_awaited_once_with(
        ANY,
        resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol.UpdateCampaignStatusRequest(
            campaign_id=SearchCampaignID.from_uuid(campaign.id),
            status=SearchCampaignStatus.COMPLETED,
        ),
    )

    handler_outbox_repo.update_task.assert_awaited_once_with(
        ANY,
        OutboxTaskRepositoryProtocol.UpdateTaskRequest(
            id=mock_resume_search_scan_task.id,
            status=OutboxTaskStatus.SUCCEEDED,
        ),
    )


async def test_handle_fails_task_when_max_retries_exceeded(
    resume_search_scan_handler_container: "AsyncContainer",
    mock_resume_search_scan_task: OutboxTask,
) -> None:
    """Test that handle marks task as failed when max retries is exceeded."""
    handler = await resume_search_scan_handler_container.get(
        resume_search_scan_handler.ResumeSearchScanHandler[AsyncSession]
    )

    campaign_id = SearchCampaignID()
    campaign = SearchCampaign(
        id=campaign_id,
        user_id="user_1",
        vacancy_id="vacancy_123",
        status=SearchCampaignStatus.ACTIVE,
        active_until=datetime.now(UTC) + timedelta(days=1),
        daily_limit=100,
        search_params=[],
    )
    payload = ResumeSearchScanPayload(campaign_id=campaign_id)
    now = datetime.now(UTC)
    task_with_max_retries = OutboxTask(
        id=mock_resume_search_scan_task.id,
        task_type=mock_resume_search_scan_task.task_type,
        payload=payload.model_dump(mode="json"),
        created_at=now,
        updated_at=now,
        available_at=now,
        attempts=99,
        status=OutboxTaskStatus.PENDING,
    )

    mock_session = cast("AsyncSession", Mock())
    ctx = OutboxContext(session=mock_session)

    mock_resume_search_scan_repository = cast("Mock", handler._resume_search_scan_repository)
    mock_resume_search_scan_repository.get_campaign = AsyncMock(return_value=campaign)

    @asynccontextmanager
    async def _outbox_context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    handler_outbox_repo = cast("Mock", handler._outbox_repo)
    handler_outbox_repo.context = _outbox_context
    handler_outbox_repo.update_task = AsyncMock(return_value=task_with_max_retries)

    mock_get_tokens_usecase = cast("Mock", handler._get_tokens_usecase)
    mock_get_tokens_usecase.get_tokens = AsyncMock()

    await handler.handle(ctx=ctx, task=task_with_max_retries)

    mock_resume_search_scan_repository.get_campaign.assert_awaited_once()

    # Verify task was marked as failed
    handler_outbox_repo.update_task.assert_awaited_once()
    await_args = handler_outbox_repo.update_task.await_args
    assert await_args is not None
    task_request = await_args.args[1]
    assert task_request.status == OutboxTaskStatus.FAILED

    mock_get_tokens_usecase.get_tokens.assert_not_called()
    mock_resume_search_scan_repository.mark_candidate_processed.assert_not_called()
