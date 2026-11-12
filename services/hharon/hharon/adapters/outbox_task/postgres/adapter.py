from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, final, override

from hharon.infra.postgres import AsyncSessionFactory

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.adapters.postgres_models.models import OutboxTaskORM
from hharon.domain.outbox_task import OutboxTask, OutboxTaskStatus, OutboxTaskType
from hharon.protocols.outbox_task.protocol import OutboxTaskRepositoryProtocol


@final
class PostgresOutboxTaskRepositoryAdapter(OutboxTaskRepositoryProtocol[AsyncSession]):
    def __init__(self, session_factory: AsyncSessionFactory) -> None:
        self._session_factory = session_factory

    @override
    @asynccontextmanager
    async def context(self) -> AsyncGenerator[AsyncSession]:
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @override
    async def create_task(
        self, session: AsyncSession, request: OutboxTaskRepositoryProtocol.CreateTaskRequest
    ) -> OutboxTask:
        model = OutboxTaskORM(
            task_type=request.task_type,
            payload=request.payload,
            available_at=request.available_at,
            attempts=0,
            status=request.status,
        )
        session.add(model)
        await session.flush()
        return model.to_domain()

    @override
    async def read_task(
        self, session: AsyncSession, request: OutboxTaskRepositoryProtocol.ReadTaskRequest
    ) -> OutboxTask:
        stmt = sa.select(OutboxTaskORM).where(OutboxTaskORM.id == request.id)
        if request.for_update:
            stmt = stmt.with_for_update()
        result = await session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError("Task not found")
        return model.to_domain()

    @override
    async def update_task(
        self, session: AsyncSession, request: OutboxTaskRepositoryProtocol.UpdateTaskRequest
    ) -> OutboxTask:
        result = await session.execute(
            sa.select(OutboxTaskORM).where(OutboxTaskORM.id == request.id).with_for_update(skip_locked=True)
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError("Task not found")

        if request.task_type is not None:
            model.task_type = request.task_type
        if request.payload is not None:
            model.payload = request.payload
        if request.available_at is not None:
            model.available_at = request.available_at
        if request.attempts is not None:
            model.attempts = request.attempts
        if request.status is not None:
            model.status = request.status

        await session.flush()
        return model.to_domain()

    @override
    async def retrieve_ready_tasks(
        self, session: AsyncSession, request: OutboxTaskRepositoryProtocol.RetrieveReadyTasks
    ) -> list[OutboxTask]:
        picked = (
            sa
            .select(OutboxTaskORM.id)
            .where(
                OutboxTaskORM.status == OutboxTaskStatus.PENDING,
                OutboxTaskORM.available_at <= datetime.now(UTC),
            )
            .order_by(OutboxTaskORM.available_at.asc(), OutboxTaskORM.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(request.limit)
            .cte("picked")
        )
        stmt = (
            sa
            .update(OutboxTaskORM)
            .where(OutboxTaskORM.id.in_(sa.select(picked.c.id)))
            .values(
                status=OutboxTaskStatus.RUNNING,
                attempts=OutboxTaskORM.attempts + 1,
            )
            .returning(OutboxTaskORM)
        )

        result = await session.execute(stmt)
        models = result.scalars().all()
        return [model.to_domain() for model in models]

    @override
    async def cancel_pending_token_update_tasks_for_user(
        self,
        session: AsyncSession,
        request: OutboxTaskRepositoryProtocol.CancelPendingTokenUpdateTasksRequest,
    ) -> int:
        stmt = (
            sa
            .update(OutboxTaskORM)
            .where(
                OutboxTaskORM.task_type == OutboxTaskType.TOKEN_UPDATE,
                OutboxTaskORM.status == OutboxTaskStatus.PENDING,
                OutboxTaskORM.payload["user_id"].astext == request.user_id,  # pyright: ignore[reportAny]
            )
            .values(status=OutboxTaskStatus.CANCELLED)
        )
        result = await session.execute(stmt)
        return result.rowcount or 0  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue,reportUnknownVariableType]
