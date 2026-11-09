from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from dishka import AsyncContainer, Provider, make_async_container
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.domain.outbox_task import OutboxTask, OutboxTaskStatus, OutboxTaskType
from hharon.domain.scalars import TaskID
from hharon.protocols.outbox_task.protocol import OutboxTaskRepositoryProtocol
from hharon.usecases.outbox_task.usecase import OutboxUsecase


@pytest.fixture
def mock_outbox_repo() -> Mock:
    """Mock OutboxTaskRepositoryProtocol с настроенными async-методами."""
    repo = Mock(spec=OutboxTaskRepositoryProtocol[AsyncSession])
    repo.update_task = AsyncMock()
    return repo


@pytest.fixture
def outbox_usecase(mock_outbox_repo: Mock) -> OutboxUsecase[AsyncSession]:
    """OutboxUsecase с mock-репозиторием."""
    return OutboxUsecase[AsyncSession](
        outbox_repo=cast("OutboxTaskRepositoryProtocol[AsyncSession]", mock_outbox_repo),
    )


def make_outbox_task(
    *,
    task_id: TaskID | None = None,
    status: OutboxTaskStatus = OutboxTaskStatus.PENDING,
    attempts: int | None = None,
) -> OutboxTask:
    """Фабрика для создания OutboxTask в тестах."""
    tid = task_id or TaskID.from_uuid(uuid4())
    now = datetime.now(UTC)
    return OutboxTask(
        id=tid,
        task_type=OutboxTaskType.TOKEN_UPDATE,
        payload={"user_id": "user123"},
        created_at=now,
        updated_at=now,
        available_at=now,
        attempts=attempts if attempts else 0,
        status=status,
    )


def make_single_session_context(session: Mock):
    """Создаёт context manager, возвращающий один session."""

    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        yield session

    return _context


def make_dual_session_context(session: Mock, session_inner: Mock):
    """Создаёт context manager: при первом вызове yields session, при втором — session_inner."""
    call_count = 0

    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        nonlocal call_count
        call_count += 1
        yield session if call_count == 1 else session_inner

    return _context


def setup_outbox_task_provider(
    base_provider: Provider,
    mock_outbox_repository: Mock,
) -> Provider:
    """Fixture to create dishka provider with OutboxUsecase dependencies."""
    provider = base_provider

    _ = provider.provide(
        source=staticmethod(lambda: mock_outbox_repository),
        provides=OutboxTaskRepositoryProtocol[AsyncSession],
    )

    usecase = OutboxUsecase[AsyncSession](outbox_repo=mock_outbox_repository)
    _ = provider.provide(
        source=staticmethod(lambda: usecase),
        provides=OutboxUsecase[AsyncSession],
    )

    return provider


@pytest.fixture
async def setup_outbox_task_container(
    setup_outbox_task_provider: Provider,
) -> AsyncIterator["AsyncContainer"]:
    """Fixture to create dishka container with OutboxUsecase dependencies."""
    container = make_async_container(setup_outbox_task_provider)
    async with container() as request_container:
        yield request_container
    await container.close()
