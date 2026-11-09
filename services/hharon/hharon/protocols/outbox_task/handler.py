from dataclasses import dataclass
from typing import Protocol

from hharon.domain.outbox_task import OutboxTask


@dataclass(frozen=True, slots=True)
class OutboxContext[SessionT]:
    # make sure session is in transaction
    session: SessionT


class TaskHandler[SessionT](Protocol):
    """Protocol for outbox task handlers with handle method."""

    async def handle(
        self,
        *,
        ctx: OutboxContext[SessionT],
        task: OutboxTask,
    ) -> None:
        """Handle an outbox task execution.

        Args:
            ctx: Outbox context with session
            task: The task to handle
        """
        ...
