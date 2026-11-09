from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.domain.outbox_task import OutboxTask, OutboxTaskStatus, OutboxTaskType
from hharon.domain.response_collection import ResponseCollectionSettings, ResponseCollectionStatus
from hharon.domain.scalars import ResponseCollectionSettingsID, TaskID
from hharon.usecases import response_collection

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.mark.asyncio
async def test_init_creates_new_settings_and_task(
    setup_response_collection_container: "AsyncContainer",
    mock_response_collection_repository: Mock,
    mock_outbox_repository: Mock,
) -> None:
    """Test that init creates new settings and task when settings don't exist."""
    usecase = await setup_response_collection_container.get(response_collection.InitResponseCollection[AsyncSession])

    user_id = "user_123"
    vacancy_id = "vacancy_123"
    headhunter_vacancy_id = "hh_vacancy_456"
    headhunter_collections = ["collection_1", "collection_2"]
    settings_id = ResponseCollectionSettingsID()
    task_id = TaskID()

    # Mock context manager
    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    mock_response_collection_repository.context = _context
    mock_response_collection_repository.get_settings_by_vacancy = AsyncMock(return_value=None)
    mock_response_collection_repository.create_settings = AsyncMock(
        return_value=ResponseCollectionSettings(
            id=settings_id,
            vacancy_id=vacancy_id,
            user_id=user_id,
            headhunter_vacancy_id=headhunter_vacancy_id,
            headhunter_collections=headhunter_collections,
            status=ResponseCollectionStatus.ACTIVE,
        )
    )

    # Mock outbox repository
    @asynccontextmanager
    async def _outbox_context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    mock_outbox_repository.context = _outbox_context
    mock_outbox_repository.create_task = AsyncMock(
        return_value=OutboxTask(
            id=task_id,
            task_type=OutboxTaskType.RESPONSE_COLLECTION,
            payload={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            available_at=datetime.now(UTC),
            attempts=0,
            status=OutboxTaskStatus.PENDING,
        )
    )

    request = response_collection.InitResponseCollection.InitResponseCollectionRequest(
        user_id=user_id,
        vacancy_id=vacancy_id,
        hh_vacancy_id=headhunter_vacancy_id,
        hh_collections=headhunter_collections,
    )

    result = await usecase.init(request)

    assert result.vacancy_id == vacancy_id
    mock_response_collection_repository.get_settings_by_vacancy.assert_awaited_once()
    mock_response_collection_repository.create_settings.assert_awaited_once()
    mock_outbox_repository.create_task.assert_awaited_once()


@pytest.mark.asyncio
async def test_init_uses_existing_settings_and_creates_task(
    setup_response_collection_container: "AsyncContainer",
    mock_response_collection_repository: Mock,
    mock_outbox_repository: Mock,
) -> None:
    """Test that init uses existing settings and creates new task when settings exist."""
    usecase = await setup_response_collection_container.get(response_collection.InitResponseCollection[AsyncSession])

    user_id = "user_123"
    vacancy_id = "vacancy_123"
    headhunter_vacancy_id = "hh_vacancy_456"
    headhunter_collections = ["collection_1", "collection_2"]
    settings_id = ResponseCollectionSettingsID()
    task_id = TaskID()

    existing_settings = ResponseCollectionSettings(
        id=settings_id,
        vacancy_id=vacancy_id,
        user_id=user_id,
        headhunter_vacancy_id=headhunter_vacancy_id,
        headhunter_collections=headhunter_collections,
        status=ResponseCollectionStatus.ACTIVE,
    )

    # Mock context manager
    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    mock_response_collection_repository.context = _context
    mock_response_collection_repository.get_settings_by_vacancy = AsyncMock(return_value=existing_settings)

    # Mock outbox repository
    @asynccontextmanager
    async def _outbox_context() -> AsyncIterator[Mock]:
        session = Mock()
        yield session

    mock_outbox_repository.context = _outbox_context
    mock_outbox_repository.create_task = AsyncMock(
        return_value=OutboxTask(
            id=task_id,
            task_type=OutboxTaskType.RESPONSE_COLLECTION,
            payload={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            available_at=datetime.now(UTC),
            attempts=0,
            status=OutboxTaskStatus.PENDING,
        )
    )

    request = response_collection.InitResponseCollection.InitResponseCollectionRequest(
        user_id=user_id,
        vacancy_id=vacancy_id,
        hh_vacancy_id=headhunter_vacancy_id,
        hh_collections=headhunter_collections,
    )

    result = await usecase.init(request)

    assert result.vacancy_id == vacancy_id
    mock_response_collection_repository.get_settings_by_vacancy.assert_awaited_once()
    mock_response_collection_repository.create_settings.assert_not_called()
    mock_outbox_repository.create_task.assert_awaited_once()


@pytest.mark.asyncio
async def test_init_raises_error_on_exception(
    setup_response_collection_container: "AsyncContainer",
    mock_response_collection_repository: Mock,
) -> None:
    """Test that init raises InitResponseCollectionError on exception."""
    usecase = await setup_response_collection_container.get(response_collection.InitResponseCollection[AsyncSession])

    user_id = "user_123"

    # Mock context manager that raises exception
    async def _context() -> AsyncIterator[Mock]:
        raise ValueError("Database error")
        yield  # pyright: ignore[reportUnreachable]

    mock_response_collection_repository.context = _context

    request = response_collection.InitResponseCollection.InitResponseCollectionRequest(
        user_id=user_id,
        vacancy_id="vacancy_123",
        hh_vacancy_id="hh_vacancy_456",
        hh_collections=["collection_1"],
    )

    with pytest.raises(response_collection.InitResponseCollectionError):
        await usecase.init(request)
