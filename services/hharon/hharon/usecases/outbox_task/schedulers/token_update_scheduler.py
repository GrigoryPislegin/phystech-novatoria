from datetime import datetime
from typing import final

import structlog

from hharon.domain.outbox_task import OutboxTaskType, TokenUpdatePayload
from hharon.protocols.outbox_task import OutboxContext
from hharon.protocols.outbox_task.protocol import OutboxTaskRepositoryProtocol
from hharon.usecases.outbox_task.usecase import OutboxUsecase

log = structlog.stdlib.get_logger("hharon.usecases.outbox_task.schedulers.TokenUpdateScheduler")


class TokenUpdateSchedulerError(Exception):
    """Base exception class for TokenUpdateScheduler errors."""


class TokenUpdateSchedulerScheduleError(TokenUpdateSchedulerError):
    """Schedule task error raised by TokenUpdateScheduler."""


@final
class TokenUpdateScheduler[SessionT]:
    """Scheduler for TOKEN_UPDATE outbox tasks."""

    def __init__(
        self,
        *,
        outbox_usecase: OutboxUsecase[SessionT],
        outbox_repo: OutboxTaskRepositoryProtocol[SessionT],
    ) -> None:
        self._outbox_usecase = outbox_usecase
        self._outbox_repo = outbox_repo

    async def cancel_pending_for_user(self, *, ctx: OutboxContext[SessionT], user_id: str) -> int:
        log.debug("Cancelling pending token update tasks", user_id=user_id)
        cancelled = await self._outbox_repo.cancel_pending_token_update_tasks_for_user(
            ctx.session,
            OutboxTaskRepositoryProtocol.CancelPendingTokenUpdateTasksRequest(user_id=user_id),
        )
        if cancelled > 0:
            log.info("Cancelled pending token update tasks", user_id=user_id, count=cancelled)
        return cancelled

    async def schedule(
        self,
        *,
        ctx: OutboxContext[SessionT],
        user_id: str,
        expires_at: datetime,
    ) -> None:
        """Schedule a token refresh task in the outbox.

        Args:
            ctx: Outbox context with session
            user_id: User ID for the task
            expires_at: When the task should be available for execution
        """
        log.debug("Scheduling token refresh task", user_id=user_id, expires_at=expires_at)
        try:
            payload = TokenUpdatePayload(user_id=user_id)
            _ = await self._outbox_usecase.schedule_task(
                ctx=ctx,
                request=OutboxUsecase.ScheduleTaskRequest(
                    task_type=OutboxTaskType.TOKEN_UPDATE,
                    payload=payload.model_dump(mode="json"),
                    available_at=expires_at,
                ),
            )
            log.info("Successfully scheduled token refresh task", user_id=user_id, expires_at=expires_at)
        except Exception as e:
            log.exception("failed to schedule token refresh task", user_id=user_id)
            error_msg = f"failed to schedule token refresh task: {e!s}"
            raise TokenUpdateSchedulerScheduleError(error_msg) from e
