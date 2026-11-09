from __future__ import annotations

from typing import TYPE_CHECKING, final

from hharon.domain.outbox_task import OutboxTaskType

if TYPE_CHECKING:
    from hharon.protocols.outbox_task.handler import TaskHandler


class TaskHandlerManagerError(Exception):
    """Base exception class for TaskHandlerManager errors."""


class TaskHandlerNotFoundError(TaskHandlerManagerError):
    """Handler not found for task type."""


@final
class TaskHandlerManager[SessionT]:
    """Manager for getting task handlers by task type."""

    def __init__(self, handlers: dict[OutboxTaskType, TaskHandler[SessionT]]) -> None:
        """Initialize manager with handlers mapping.

        Args:
            handlers: Dictionary mapping task types to their handlers
        """
        self._handlers = handlers

    def get_handler_for(self, task_type: OutboxTaskType) -> TaskHandler[SessionT]:
        """Get handler for the given task type.

        Args:
            task_type: The type of task to get handler for

        Returns:
            Task handler for the given task type

        Raises:
            TaskHandlerNotFoundError: If no handler is found for the task type
        """
        handler = self._handlers.get(task_type)
        if handler is None:
            error_msg = f"No handler found for task type: {task_type}"
            raise TaskHandlerNotFoundError(error_msg)
        return handler
