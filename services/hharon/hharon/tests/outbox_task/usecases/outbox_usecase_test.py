from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.domain.outbox_task import OutboxTaskStatus
from hharon.protocols.outbox_task.protocol import OutboxTaskRepositoryProtocol
from hharon.tests.outbox_task.usecases.conftest import (
    make_dual_session_context,
    make_outbox_task,
    make_single_session_context,
)
from hharon.usecases.outbox_task.usecase import OutboxUsecase


@pytest.mark.asyncio
async def test_context_success_updates_task_to_succeeded(
    outbox_usecase: OutboxUsecase[AsyncSession],
    mock_outbox_repo: Mock,
) -> None:
    """При успешном выполнении context обновляет задачу в статус SUCCEEDED."""
    session = Mock()
    task = make_outbox_task(status=OutboxTaskStatus.RUNNING)
    current_task = make_outbox_task(task_id=task.id, status=OutboxTaskStatus.RUNNING)

    mock_outbox_repo.context = make_single_session_context(session)
    mock_outbox_repo.read_task = AsyncMock(return_value=current_task)

    async with outbox_usecase.context(task) as ctx:
        assert ctx.session is session

    mock_outbox_repo.read_task.assert_awaited_once_with(
        session,
        OutboxTaskRepositoryProtocol.ReadTaskRequest(id=task.id, for_update=True),
    )
    mock_outbox_repo.update_task.assert_awaited_once()
    call_args = mock_outbox_repo.update_task.call_args
    assert call_args[0][1].id == task.id
    assert call_args[0][1].status == OutboxTaskStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_context_on_exception_rolls_back_to_pending_when_status_not_failed(
    outbox_usecase: OutboxUsecase[AsyncSession],
    mock_outbox_repo: Mock,
) -> None:
    """При исключении: если статус задачи !=FAILED — обновляем в PENDING."""
    session = Mock()
    session_inner = Mock()
    task = make_outbox_task(status=OutboxTaskStatus.RUNNING, attempts=0)
    current_task = make_outbox_task(task_id=task.id, status=OutboxTaskStatus.PENDING, attempts=0)

    mock_outbox_repo.context = make_dual_session_context(session, session_inner)
    mock_outbox_repo.read_task = AsyncMock(return_value=current_task)
    mock_outbox_repo.update_task = AsyncMock()

    with pytest.raises(ValueError, match="boom"):
        async with outbox_usecase.context(task):
            raise ValueError("boom")

    mock_outbox_repo.read_task.assert_awaited_once_with(
        session_inner,
        OutboxTaskRepositoryProtocol.ReadTaskRequest(id=task.id, for_update=True),
    )
    mock_outbox_repo.update_task.assert_awaited_once_with(
        session_inner,
        OutboxTaskRepositoryProtocol.UpdateTaskRequest(id=task.id, status=OutboxTaskStatus.PENDING, attempts=1),
    )


@pytest.mark.asyncio
async def test_context_on_exception_does_not_update_when_status_already_failed(
    outbox_usecase: OutboxUsecase[AsyncSession],
    mock_outbox_repo: Mock,
) -> None:
    """При исключении: если статус уже FAILED — update_task не вызывается."""
    session = Mock()
    session_inner = Mock()
    task = make_outbox_task(status=OutboxTaskStatus.RUNNING)
    current_task = make_outbox_task(task_id=task.id, status=OutboxTaskStatus.FAILED)

    mock_outbox_repo.context = make_dual_session_context(session, session_inner)
    mock_outbox_repo.read_task = AsyncMock(return_value=current_task)
    mock_outbox_repo.update_task = AsyncMock()

    with pytest.raises(RuntimeError):
        async with outbox_usecase.context(task):
            raise RuntimeError("handler failed")

    mock_outbox_repo.read_task.assert_awaited_once_with(
        session_inner,
        OutboxTaskRepositoryProtocol.ReadTaskRequest(id=task.id, for_update=True),
    )
    mock_outbox_repo.update_task.assert_not_called()


@pytest.mark.asyncio
async def test_context_on_exception_read_task_uses_for_update(
    outbox_usecase: OutboxUsecase[AsyncSession],
    mock_outbox_repo: Mock,
) -> None:
    """При исключении read_task вызывается с for_update=True для блокировки строки."""
    session = Mock()
    session_inner = Mock()
    task = make_outbox_task()

    mock_outbox_repo.context = make_dual_session_context(session, session_inner)
    mock_outbox_repo.read_task = AsyncMock(return_value=make_outbox_task(status=OutboxTaskStatus.PENDING))
    mock_outbox_repo.update_task = AsyncMock()

    with pytest.raises(ValueError, match="any error"):
        async with outbox_usecase.context(task):
            raise ValueError("any error")

    read_call = mock_outbox_repo.read_task.call_args
    assert read_call[0][1].for_update is True
