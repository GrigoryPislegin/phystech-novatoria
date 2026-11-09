from __future__ import annotations

import contextlib
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, final

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from hharon.domain.outbox_task import OutboxTask, OutboxTaskStatus, OutboxTaskType
from hharon.domain.scalars import TaskID
from hharon.protocols.outbox_task import OutboxContext
from hharon.protocols.outbox_task.protocol import OutboxTaskRepositoryProtocol


@final
class OutboxUsecase[SessionT]:
    def __init__(self, outbox_repo: OutboxTaskRepositoryProtocol[SessionT]) -> None:
        self._outbox_repo = outbox_repo

    @asynccontextmanager
    async def context(self, task: OutboxTask) -> AsyncIterator[OutboxContext[SessionT]]:
        async with self._outbox_repo.context() as session:
            try:
                yield OutboxContext[SessionT](session=session)

            except Exception as e:
                async with self._outbox_repo.context() as session_inner:
                    current_task = await self._outbox_repo.read_task(
                        session_inner,
                        OutboxTaskRepositoryProtocol.ReadTaskRequest(id=task.id, for_update=True),
                    )
                    if current_task.status != OutboxTaskStatus.FAILED:
                        _ = await self._outbox_repo.update_task(
                            session_inner,
                            OutboxTaskRepositoryProtocol.UpdateTaskRequest(
                                id=task.id,
                                status=OutboxTaskStatus.PENDING,
                                attempts=task.attempts + 1
                                if task.attempts == current_task.attempts
                                else current_task.attempts,
                            ),
                        )
                raise e from e
            else:
                current_task = await self._outbox_repo.read_task(
                    session,
                    OutboxTaskRepositoryProtocol.ReadTaskRequest(id=task.id, for_update=True),
                )

                is_task_not_failed = current_task.status in {OutboxTaskStatus.RUNNING, OutboxTaskStatus.PENDING}
                is_task_in_past = current_task.available_at < datetime.now(UTC)

                if is_task_not_failed and is_task_in_past:
                    _ = await self._outbox_repo.update_task(
                        session,
                        OutboxTaskRepositoryProtocol.UpdateTaskRequest(id=task.id, status=OutboxTaskStatus.SUCCEEDED),
                    )

    @dataclass(frozen=True)
    class ScheduleTaskRequest:
        task_type: OutboxTaskType
        payload: dict[str, Any]  # pyright: ignore[reportExplicitAny]
        available_at: datetime

    async def schedule_task(self, ctx: OutboxContext[SessionT] | None, request: ScheduleTaskRequest) -> OutboxTask:
        async with contextlib.AsyncExitStack() as deferexit:
            session: SessionT = ctx.session if ctx else await deferexit.enter_async_context(self._outbox_repo.context())

            return await self._outbox_repo.create_task(
                session,
                OutboxTaskRepositoryProtocol.CreateTaskRequest(
                    task_type=request.task_type,
                    payload=request.payload,
                    available_at=request.available_at,
                    status=OutboxTaskStatus.PENDING,
                ),
            )

    @dataclass(frozen=True)
    class RetrieveReadyTasksRequest:
        limit: int

    async def retrieve_ready_tasks(self, request: RetrieveReadyTasksRequest) -> list[OutboxTask]:
        async with self._outbox_repo.context() as session:
            return await self._outbox_repo.retrieve_ready_tasks(
                session,
                OutboxTaskRepositoryProtocol.RetrieveReadyTasks(
                    limit=request.limit,
                ),
            )

    @dataclass(frozen=True)
    class UpdateTaskRequest:
        id: TaskID
        task_type: OutboxTaskType | None = None
        payload: dict[str, Any] | None = None  # pyright: ignore[reportExplicitAny]
        available_at: datetime | None = None
        attempts: int | None = None
        status: OutboxTaskStatus | None = None

    async def update_task(self, ctx: OutboxContext[SessionT], request: UpdateTaskRequest) -> OutboxTask:
        return await self._outbox_repo.update_task(
            ctx.session,
            OutboxTaskRepositoryProtocol.UpdateTaskRequest(
                id=request.id,
                task_type=request.task_type,
                payload=request.payload,
                available_at=request.available_at,
                attempts=request.attempts,
                status=request.status,
            ),
        )
