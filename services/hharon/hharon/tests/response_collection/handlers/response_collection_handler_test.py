from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.adapters import HeadHunterResponseCollectionAdapter
from hharon.domain.outbox_task import OutboxTask, OutboxTaskStatus, ResponseCollectionPayload
from hharon.domain.response_collection import ResponseCollectionSettings, ResponseCollectionStatus
from hharon.domain.scalars import ResponseCollectionSettingsID
from hharon.pkg.hhapi.models import (
    Item2,
    NegotiationsObjectsEmployerTopicResume,
    ResumeResumeForEmployer,
)
from hharon.protocols.response_collection import HeadHunterAccessDeniedError, HeadHunterRateLimitError
from hharon.usecases.outbox_task.handlers import response_collection_handler
from hharon.usecases.outbox_task.usecase import OutboxContext
from hharon.usecases.token import get_tokens

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.mark.asyncio
async def test_handle_raises_error_when_settings_not_found(
    response_collection_handler_container: "AsyncContainer",
    mock_response_collection_repository: Mock,
    mock_task: OutboxTask,
) -> None:
    """Test that handle raises error when settings not found."""
    handler = await response_collection_handler_container.get(
        response_collection_handler.ResponseCollectionHandler[AsyncSession]
    )

    mock_session = cast("AsyncSession", Mock())
    ctx = OutboxContext(session=mock_session)

    mock_response_collection_repository.get_settings = AsyncMock(return_value=None)

    with pytest.raises(response_collection_handler.ResponseCollectionHandlerNotFoundError):
        await handler.handle(ctx=ctx, task=mock_task)


@pytest.mark.asyncio
async def test_handle_processes_responses_successfully(
    response_collection_handler_container: "AsyncContainer",
    mock_response_collection_repository: Mock,
    mock_task: OutboxTask,
) -> None:
    """Test that handle processes responses successfully."""
    handler = await response_collection_handler_container.get(
        response_collection_handler.ResponseCollectionHandler[AsyncSession]
    )

    settings_id = ResponseCollectionSettingsID()
    user_id = "user_123"
    settings = ResponseCollectionSettings(
        id=settings_id,
        vacancy_id="vacancy_123",
        user_id=user_id,
        headhunter_vacancy_id="hh_vacancy_456",
        headhunter_collections=["collection_1"],
        status=ResponseCollectionStatus.ACTIVE,
    )

    # Mock resume
    resume = Mock(spec=NegotiationsObjectsEmployerTopicResume)
    resume.id = "resume_789"

    # Mock response item
    response_item = Mock(spec=Item2)
    response_item.resume = resume

    mock_session = cast("AsyncSession", Mock())
    ctx = OutboxContext(session=mock_session)

    # Setup async context manager for repository
    @asynccontextmanager
    async def _repo_context() -> AsyncIterator[Mock]:
        yield mock_session

    # Setup mocks
    mock_response_collection_repository.get_settings = AsyncMock(return_value=settings)
    mock_response_collection_repository.is_candidate_processed = AsyncMock(return_value=False)
    mock_response_collection_repository.context = _repo_context
    mock_response_collection_repository.mark_candidate_processed = AsyncMock(
        return_value=Mock(
            resume_id="resume_789",
            vacancy_id=settings.vacancy_id,
        )
    )

    get_tokens_usecase = await response_collection_handler_container.get(get_tokens.GetTokens)
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

    # Mock HH adapter - need to properly mock async generator
    hh_adapter = Mock(spec=HeadHunterResponseCollectionAdapter)

    async def _get_responses(collection_id: str, vacancy_id: str, access_token: str) -> AsyncIterator[Item2]:  # noqa: ARG001
        yield response_item

    hh_adapter.get_responses_from_collection = _get_responses

    # Create fully mocked ResumeResumeForEmployer with all required attributes
    mock_resume = Mock(spec=ResumeResumeForEmployer)
    mock_resume.model_dump_json = Mock(return_value='{"id": "resume_789"}')
    mock_resume.first_name = "Иван"
    mock_resume.last_name = "Иванов"
    mock_resume.middle_name = "Иванович"
    mock_resume.area = SimpleNamespace(name="Москва")
    mock_resume.gender = SimpleNamespace(id="male")
    mock_resume.age = 30
    mock_resume.title = "Разработчик"
    mock_resume.total_experience = SimpleNamespace(months=60)
    mock_resume.experience = []
    mock_resume.skill_set = ["Python", "SQL"]
    mock_resume.skills = "Опыт работы с Python"
    mock_resume.driver_license_types = []
    mock_resume.education = SimpleNamespace(level=None, primary=[], elementary=[], additional=[], attestation=[])
    mock_resume.language = []
    mock_resume.contact = []
    mock_resume.salary = None
    mock_resume.alternate_url = "https://hh.ru/resume/123"

    hh_adapter.get_resume = AsyncMock(return_value=mock_resume)

    # Mock outbox usecase
    handler_outbox_usecase = cast("Mock", handler._outbox_usecase)
    handler_outbox_usecase.update_task = AsyncMock(return_value=mock_task)
    handler_outbox_usecase.schedule_task = AsyncMock(return_value=mock_task)

    # Patch handler's _hh_client to use our mock
    handler._hh_client = hh_adapter

    await handler.handle(ctx=ctx, task=mock_task)

    mock_response_collection_repository.get_settings.assert_awaited_once()
    mock_response_collection_repository.is_candidate_processed.assert_awaited_once()
    mock_response_collection_repository.mark_candidate_processed.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_handles_rate_limit_error(
    response_collection_handler_container: "AsyncContainer",
    mock_response_collection_repository: Mock,
    mock_task: OutboxTask,
) -> None:
    """Test that handle handles rate limit error correctly."""
    handler = await response_collection_handler_container.get(
        response_collection_handler.ResponseCollectionHandler[AsyncSession]
    )

    settings_id = ResponseCollectionSettingsID()
    user_id = "user_123"
    settings = ResponseCollectionSettings(
        id=settings_id,
        vacancy_id="vacancy_123",
        user_id=user_id,
        headhunter_vacancy_id="hh_vacancy_456",
        headhunter_collections=["collection_1"],
        status=ResponseCollectionStatus.ACTIVE,
    )

    mock_session = cast("AsyncSession", Mock())
    ctx = OutboxContext(session=mock_session)

    mock_response_collection_repository.get_settings = AsyncMock(return_value=settings)

    # Mock get_tokens usecase
    get_tokens_usecase = await response_collection_handler_container.get(get_tokens.GetTokens)
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

    # Mock HH adapter to raise rate limit error
    hh_adapter = Mock(spec=HeadHunterResponseCollectionAdapter)

    async def _get_responses(collection_id: str, vacancy_id: str, access_token: str) -> AsyncIterator[Item2]:  # noqa: ARG001
        raise HeadHunterRateLimitError("Rate limit", retry_after=60)
        yield  # Make it a generator

    hh_adapter.get_responses_from_collection = _get_responses
    handler._hh_client = hh_adapter

    # Mock outbox repository for reschedule
    @asynccontextmanager
    async def _outbox_context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    handler_outbox_repo = handler._outbox_repo
    handler_outbox_repo.context = _outbox_context  # type: ignore[assignment]
    handler_outbox_repo.update_task = AsyncMock(return_value=mock_task)  # type: ignore[assignment]

    with pytest.raises(HeadHunterRateLimitError):
        await handler.handle(ctx=ctx, task=mock_task)

    # Verify task was rescheduled
    handler_outbox_repo.update_task.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_handles_collection_access_denied_error(
    response_collection_handler_container: "AsyncContainer",
    mock_response_collection_repository: Mock,
    mock_task: OutboxTask,
) -> None:
    """Test that handle fails task on collection access denied error."""
    handler = await response_collection_handler_container.get(
        response_collection_handler.ResponseCollectionHandler[AsyncSession]
    )

    settings_id = ResponseCollectionSettingsID()
    user_id = "user_123"
    settings = ResponseCollectionSettings(
        id=settings_id,
        vacancy_id="vacancy_123",
        user_id=user_id,
        headhunter_vacancy_id="hh_vacancy_456",
        headhunter_collections=["collection_1"],
        status=ResponseCollectionStatus.ACTIVE,
    )

    mock_session = cast("AsyncSession", Mock())
    ctx = OutboxContext(session=mock_session)

    # Setup async context manager for repository
    @asynccontextmanager
    async def _repo_context() -> AsyncIterator[Mock]:
        yield mock_session

    mock_response_collection_repository.get_settings = AsyncMock(return_value=settings)
    mock_response_collection_repository.context = _repo_context
    mock_response_collection_repository.update_settings_status = AsyncMock(return_value=None)

    # Mock get_tokens usecase
    get_tokens_usecase = await response_collection_handler_container.get(get_tokens.GetTokens)
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

    # Mock HH adapter to raise access denied error
    hh_adapter = Mock(spec=HeadHunterResponseCollectionAdapter)

    async def _get_responses(collection_id: str, vacancy_id: str, access_token: str) -> AsyncIterator[Item2]:  # noqa: ARG001
        raise HeadHunterAccessDeniedError("Access denied")
        yield  # Make it a generator

    hh_adapter.get_responses_from_collection = _get_responses
    handler._hh_client = hh_adapter

    # Mock outbox repo and response collection repo for fail task
    @asynccontextmanager
    async def _outbox_context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    handler_outbox_repo = handler._outbox_repo
    handler_outbox_repo.context = _outbox_context  # type: ignore[assignment]
    handler_outbox_repo.update_task = AsyncMock(return_value=mock_task)  # type: ignore[assignment]

    with pytest.raises(response_collection_handler.ResponseCollectionHandlerAccessDeniedError):
        await handler.handle(ctx=ctx, task=mock_task)

    # Verify task was marked as failed
    handler_outbox_repo.update_task.assert_awaited_once()
    await_args = handler_outbox_repo.update_task.await_args
    assert await_args is not None
    task_request = await_args.args[1]
    assert task_request.status == OutboxTaskStatus.FAILED

    # Verify settings were marked as failed
    mock_response_collection_repository.update_settings_status.assert_awaited_once()
    settings_update_args = mock_response_collection_repository.update_settings_status.await_args
    assert settings_update_args is not None
    settings_request = settings_update_args.args[1]
    assert settings_request.settings_id == settings_id
    assert settings_request.status == ResponseCollectionStatus.FAILED


@pytest.mark.asyncio
async def test_handle_skips_already_processed_candidates(
    response_collection_handler_container: "AsyncContainer",
    mock_response_collection_repository: Mock,
    mock_task: OutboxTask,
) -> None:
    """Test that handle skips already processed candidates."""
    handler = await response_collection_handler_container.get(
        response_collection_handler.ResponseCollectionHandler[AsyncSession]
    )

    settings_id = ResponseCollectionSettingsID()
    user_id = "user_123"
    settings = ResponseCollectionSettings(
        id=settings_id,
        vacancy_id="vacancy_123",
        user_id=user_id,
        headhunter_vacancy_id="hh_vacancy_456",
        headhunter_collections=["collection_1"],
        status=ResponseCollectionStatus.ACTIVE,
    )

    # Mock resume
    resume = Mock(spec=NegotiationsObjectsEmployerTopicResume)
    resume.id = "resume_789"

    # Mock response item
    response_item = Mock(spec=Item2)
    response_item.resume = resume

    mock_session = cast("AsyncSession", Mock())
    ctx = OutboxContext(session=mock_session)

    # Setup async context manager for repository
    @asynccontextmanager
    async def _repo_context() -> AsyncIterator[Mock]:
        yield mock_session

    mock_response_collection_repository.get_settings = AsyncMock(return_value=settings)
    mock_response_collection_repository.is_candidate_processed = AsyncMock(return_value=True)  # Already processed
    mock_response_collection_repository.context = _repo_context

    get_tokens_usecase = await response_collection_handler_container.get(get_tokens.GetTokens)
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

    # Mock HH adapter
    hh_adapter = Mock(spec=HeadHunterResponseCollectionAdapter)

    async def _get_responses(collection_id: str, vacancy_id: str, access_token: str) -> AsyncIterator[Item2]:  # noqa: ARG001
        yield response_item

    hh_adapter.get_responses_from_collection = _get_responses
    handler._hh_client = hh_adapter

    # Mock outbox usecase
    handler_outbox_usecase = handler._outbox_usecase
    handler_outbox_usecase.update_task = AsyncMock(return_value=mock_task)  # type: ignore[assignment]
    handler_outbox_usecase.schedule_task = AsyncMock(return_value=mock_task)  # type: ignore[assignment]

    await handler.handle(ctx=ctx, task=mock_task)

    # Verify candidate was checked but not marked as processed
    mock_response_collection_repository.is_candidate_processed.assert_awaited_once()
    mock_response_collection_repository.mark_candidate_processed.assert_not_called()


@pytest.mark.asyncio
async def test_handle_fails_task_when_max_retries_exceeded(
    response_collection_handler_container: "AsyncContainer",
    mock_response_collection_repository: Mock,
    mock_task: OutboxTask,
) -> None:
    """Test that handle marks task as failed when max retries is exceeded."""
    handler = await response_collection_handler_container.get(
        response_collection_handler.ResponseCollectionHandler[AsyncSession]
    )

    settings_id = ResponseCollectionSettingsID()
    user_id = "user_123"
    settings = ResponseCollectionSettings(
        id=settings_id,
        vacancy_id="vacancy_123",
        user_id=user_id,
        headhunter_vacancy_id="hh_vacancy_456",
        headhunter_collections=["collection_1"],
        status=ResponseCollectionStatus.ACTIVE,
    )
    payload = ResponseCollectionPayload(settings_id=settings_id)
    now = datetime.now(UTC)
    task_with_max_retries = OutboxTask(
        id=mock_task.id,
        task_type=mock_task.task_type,
        payload=payload.model_dump(mode="json"),
        created_at=now,
        updated_at=now,
        available_at=now,
        attempts=99,
        status=OutboxTaskStatus.PENDING,
    )

    mock_session = cast("AsyncSession", Mock())
    ctx = OutboxContext(session=mock_session)

    mock_response_collection_repository.get_settings = AsyncMock(return_value=settings)

    @asynccontextmanager
    async def _outbox_context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    handler_outbox_repo = handler._outbox_repo
    handler_outbox_repo.context = _outbox_context  # type: ignore[assignment]
    handler_outbox_repo.update_task = AsyncMock(return_value=task_with_max_retries)  # type: ignore[assignment]

    mock_get_tokens_usecase = cast("Mock", handler._get_tokens_usecase)
    mock_get_tokens_usecase.get_tokens = AsyncMock()

    await handler.handle(ctx=ctx, task=task_with_max_retries)

    mock_response_collection_repository.get_settings.assert_awaited_once()

    # Verify task was marked as failed
    handler_outbox_repo.update_task.assert_awaited_once()
    await_args = handler_outbox_repo.update_task.await_args
    assert await_args is not None
    task_request = await_args.args[1]
    assert task_request.status == OutboxTaskStatus.FAILED

    mock_get_tokens_usecase.get_tokens.assert_not_called()
    mock_response_collection_repository.mark_candidate_processed.assert_not_called()
