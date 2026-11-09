from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from datetime import datetime

from hharon.domain.outbox_task import OutboxTask, OutboxTaskStatus, OutboxTaskType
from hharon.domain.scalars import TaskID


class OutboxTaskRepositoryProtocol[SessionT](Protocol):
    @asynccontextmanager
    async def context(self) -> AsyncGenerator[SessionT]:
        raise NotImplementedError("SessionProviderRepositoryProtocol.context")
        yield  # pyright: ignore[reportUnreachable]

    @dataclass
    class CreateTaskRequest:
        task_type: OutboxTaskType
        payload: dict[str, Any]  # pyright: ignore[reportExplicitAny]
        available_at: datetime
        status: OutboxTaskStatus = OutboxTaskStatus.PENDING

    async def create_task(self, session: SessionT, request: CreateTaskRequest) -> OutboxTask: ...

    @dataclass
    class ReadTaskRequest:
        id: TaskID
        for_update: bool = False

    async def read_task(self, session: SessionT, request: ReadTaskRequest) -> OutboxTask: ...

    @dataclass
    class UpdateTaskRequest:
        id: TaskID
        task_type: OutboxTaskType | None = None
        payload: dict[str, Any] | None = None  # pyright: ignore[reportExplicitAny]
        available_at: datetime | None = None
        attempts: int | None = None
        status: OutboxTaskStatus | None = None

    async def update_task(self, session: SessionT, request: UpdateTaskRequest) -> OutboxTask: ...

    @dataclass
    class RetrieveReadyTasks:
        limit: int

    async def retrieve_ready_tasks(self, session: SessionT, request: RetrieveReadyTasks) -> list[OutboxTask]: ...

    @dataclass
    class CancelPendingTokenUpdateTasksRequest:
        user_id: str

    async def cancel_pending_token_update_tasks_for_user(
        self, session: SessionT, request: CancelPendingTokenUpdateTasksRequest
    ) -> int: ...
