from unittest.mock import Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.domain.outbox_task import OutboxTaskType
from hharon.protocols.outbox_task.handler import TaskHandler
from hharon.usecases.outbox_task.manager import TaskHandlerManager, TaskHandlerNotFoundError


@pytest.fixture
def mock_token_update_handler() -> TaskHandler[AsyncSession]:
    """Fixture to create a mock TokenUpdateHandler."""
    return Mock(spec=TaskHandler[AsyncSession])


@pytest.fixture
def handler_manager(mock_token_update_handler: Mock) -> TaskHandlerManager[AsyncSession]:
    """Fixture to create TaskHandlerManager with mock handlers."""
    handlers: dict[OutboxTaskType, TaskHandler[AsyncSession]] = {
        OutboxTaskType.TOKEN_UPDATE: mock_token_update_handler,
    }
    return TaskHandlerManager[AsyncSession](handlers=handlers)


def test_get_handler_for_returns_handler_when_found(
    handler_manager: TaskHandlerManager[AsyncSession],
    mock_token_update_handler: Mock,
) -> None:
    """Test that get_handler_for returns the correct handler when found."""
    handler = handler_manager.get_handler_for(OutboxTaskType.TOKEN_UPDATE)
    assert handler is mock_token_update_handler


def test_get_handler_for_raises_error_when_handler_not_in_dict() -> None:
    """Test that get_handler_for raises TaskHandlerNotFoundError when handler not in dict."""
    # Create manager with empty dict to test error case
    handlers: dict[OutboxTaskType, TaskHandler[AsyncSession]] = {}
    manager = TaskHandlerManager[AsyncSession](handlers=handlers)

    with pytest.raises(TaskHandlerNotFoundError) as exc_info:
        _ = manager.get_handler_for(OutboxTaskType.TOKEN_UPDATE)

    assert "No handler found for task type" in str(exc_info.value)
    assert str(OutboxTaskType.TOKEN_UPDATE) in str(exc_info.value)


def test_get_handler_for_raises_error_for_empty_handlers() -> None:
    """Test that get_handler_for raises error when handlers dict is empty."""
    empty_manager = TaskHandlerManager[AsyncSession](handlers={})

    with pytest.raises(TaskHandlerNotFoundError) as exc_info:
        _ = empty_manager.get_handler_for(OutboxTaskType.TOKEN_UPDATE)

    assert "No handler found for task type" in str(exc_info.value)
    assert str(OutboxTaskType.TOKEN_UPDATE) in str(exc_info.value)


def test_get_handler_for_with_multiple_handlers() -> None:
    """Test that get_handler_for works correctly with multiple handlers."""
    handler1: TaskHandler[AsyncSession] = Mock(spec=TaskHandler[AsyncSession])

    handlers: dict[OutboxTaskType, TaskHandler[AsyncSession]] = {
        OutboxTaskType.TOKEN_UPDATE: handler1,
    }
    # Note: Currently only TOKEN_UPDATE exists in OutboxTaskType
    # When more task types are added, this test can be extended

    manager = TaskHandlerManager[AsyncSession](handlers=handlers)

    retrieved_handler = manager.get_handler_for(OutboxTaskType.TOKEN_UPDATE)
    assert retrieved_handler is handler1
