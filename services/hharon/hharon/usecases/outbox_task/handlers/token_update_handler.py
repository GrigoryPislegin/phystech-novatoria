from datetime import UTC, datetime, timedelta
from typing import final

import structlog

from hharon.domain.outbox_task import OutboxTask, OutboxTaskStatus, TokenUpdatePayload
from hharon.domain.token import TokenPair
from hharon.infra.token_update import TokenUpdateConfig
from hharon.protocols import oauth2 as oauth2_protocol
from hharon.protocols import token as token_protocol
from hharon.protocols.outbox_task.handler import OutboxContext
from hharon.protocols.outbox_task.protocol import OutboxTaskRepositoryProtocol
from hharon.usecases.crypt import CipherUsecaseDecryptError, CipherUsecaseEncryptError
from hharon.usecases.outbox_task.schedulers.token_update_scheduler import TokenUpdateScheduler
from hharon.usecases.token.refresh_tokens import RefreshTokens

log = structlog.stdlib.get_logger("hharon.usecases.outbox_task.handlers.TokenUpdateHandler")


class TokenUpdateHandlerError(Exception):
    """Base exception class for TokenUpdateHandler errors."""


class TokenUpdateHandlerNotFoundError(TokenUpdateHandlerError):
    """Tokens not found error."""


class TokenUpdateHandlerDecryptError(TokenUpdateHandlerError):
    """Decryption error raised by TokenUpdateHandler."""


class TokenUpdateHandlerEncryptError(TokenUpdateHandlerError):
    """Encryption error raised by TokenUpdateHandler."""


class TokenUpdateHandlerAPIError(TokenUpdateHandlerError):
    """API error raised by TokenUpdateHandler."""


@final
class TokenUpdateHandler[SessionT]:
    """Handler for TOKEN_UPDATE outbox tasks."""

    def __init__(
        self,
        *,
        token_repository: token_protocol.HeadHunterTokenRepositoryProtocol[SessionT],
        refresh_tokens_usecase: RefreshTokens[SessionT],
        token_update_scheduler: TokenUpdateScheduler[SessionT],
        outbox_repo: OutboxTaskRepositoryProtocol[SessionT],
        config: TokenUpdateConfig,
    ) -> None:
        self._outbox_repo = outbox_repo
        self._token_repository = token_repository
        self._refresh_tokens_usecase = refresh_tokens_usecase
        self._token_update_scheduler = token_update_scheduler
        self._config = config

    async def handle(
        self,
        *,
        ctx: OutboxContext[SessionT],
        task: OutboxTask,
    ) -> None:
        """Handle a TOKEN_UPDATE outbox task execution.

        Args:
            ctx: Outbox context with session
            task: The task to handle
        """
        payload = self._parse_task_payload(task)
        user_id = payload.user_id

        try:
            await self._process_token_refresh(ctx=ctx, task=task, user_id=user_id)
        except TokenUpdateHandlerNotFoundError:
            raise
        except CipherUsecaseDecryptError as e:
            log.exception("failed to decrypt refresh token", task_id=task.id, user_id=user_id)
            raise TokenUpdateHandlerDecryptError("failed to decrypt refresh token") from e
        except CipherUsecaseEncryptError as e:
            await self._handle_encrypt_error(task=task, user_id=user_id, error=e)
        except oauth2_protocol.OAuth2APIError as e:
            await self._handle_oauth_api_error(task=task, user_id=user_id, error=e)
        except oauth2_protocol.OAuth2Error as e:
            log.exception("failed to refresh tokens", task_id=task.id, user_id=user_id)
            error_msg = f"failed to refresh tokens: {e!s}"
            raise TokenUpdateHandlerAPIError(error_msg) from e
        except Exception as e:
            log.exception("unexpected error in token update handler", task_id=task.id, user_id=user_id)
            raise TokenUpdateHandlerError("unexpected error") from e

    def _parse_task_payload(self, task: OutboxTask) -> TokenUpdatePayload:
        """Parse task payload and return TokenUpdatePayload."""
        try:
            return TokenUpdatePayload.model_validate(task.payload)
        except Exception as e:
            log.exception("failed to parse task payload", task_id=task.id, payload=task.payload)
            raise TokenUpdateHandlerError("failed to parse task payload") from e

    def _check_retry_limit(self, *, task: OutboxTask) -> bool:
        """True if max retries exceeded, False otherwise"""
        max_retries = self._config.max_retries
        if task.attempts >= max_retries:
            log.warning(
                "max retries exceeded, failing task",
                task_id=task.id,
                attempts=task.attempts,
                max_retries=max_retries,
            )
            return True
        return False

    async def _fail_task_on_max_retries(self, *, task: OutboxTask) -> None:
        """Mark task as failed when max retries is exceeded in a separate transaction."""
        async with self._outbox_repo.context() as session:
            _ = await self._outbox_repo.update_task(
                session,
                OutboxTaskRepositoryProtocol.UpdateTaskRequest(
                    id=task.id,
                    status=OutboxTaskStatus.FAILED,
                ),
            )
        log.info(
            "task marked as failed due to max retries",
            task_id=task.id,
            attempts=task.attempts,
        )

    async def _validate_and_get_tokens(self, *, session: SessionT, user_id: str, task_id: str) -> TokenPair:
        """Validate and get tokens with lock for update."""
        token_pair = await self._token_repository.lock_tokens_for_update(
            session,
            token_protocol.HeadHunterTokenRepositoryProtocol.LockTokensRequest(user_id=user_id),
        )

        if token_pair is None:
            log.warning("Tokens not found", user_id=user_id, task_id=task_id)
            error_msg = f"Tokens not found for user_id: {user_id}"
            raise TokenUpdateHandlerNotFoundError(error_msg)

        if token_pair.is_invalid:
            log.warning("Tokens are marked as invalid", user_id=user_id, task_id=task_id)
            error_msg = f"Tokens are invalid for user_id: {user_id}"
            raise TokenUpdateHandlerNotFoundError(error_msg)

        return token_pair

    async def _process_token_refresh(
        self,
        *,
        ctx: OutboxContext[SessionT],
        task: OutboxTask,
        user_id: str,
    ) -> None:
        """Process token refresh: validate, refresh, and schedule next."""
        if self._check_retry_limit(task=task):
            await self._fail_task_on_max_retries(task=task)
            return

        log.debug("Handling token update task", task_id=task.id, user_id=user_id)

        token_pair = await self._validate_and_get_tokens(session=ctx.session, user_id=user_id, task_id=str(task.id))

        token_response = await self._refresh_tokens_usecase.refresh_and_update_tokens(
            session=ctx.session, token_pair=token_pair, user_id=user_id
        )

        expires_at = datetime.now(UTC) + timedelta(seconds=token_response.token.expires_in)
        await self._token_update_scheduler.schedule(
            ctx=ctx,
            user_id=user_id,
            expires_at=expires_at,
        )

        log.info("Successfully handled token update task", task_id=task.id, user_id=user_id)

    async def _handle_encrypt_error(self, *, task: OutboxTask, user_id: str, error: Exception) -> None:
        """Handle encryption error by marking tokens as invalid in a separate transaction."""
        log.exception("failed to encrypt new tokens", task_id=task.id, user_id=user_id)
        # Mark tokens as invalid in a separate transaction to avoid rollback
        async with self._token_repository.context() as session:
            _ = await self._token_repository.mark_tokens_invalid(
                session,
                token_protocol.HeadHunterTokenRepositoryProtocol.MarkTokensInvalidRequest(user_id=user_id),
            )
        error_msg = "failed to encrypt new tokens"
        raise TokenUpdateHandlerEncryptError(error_msg) from error

    async def _handle_oauth_api_error(self, *, task: OutboxTask, user_id: str, error: Exception) -> None:
        """Handle OAuth2 API error by marking tokens as invalid in a separate transaction."""
        log.exception("failed to refresh tokens via API", task_id=task.id, user_id=user_id)
        async with self._token_repository.context() as session:
            _ = await self._token_repository.mark_tokens_invalid(
                session,
                token_protocol.HeadHunterTokenRepositoryProtocol.MarkTokensInvalidRequest(user_id=user_id),
            )
        error_msg = f"failed to refresh tokens via API: {error!s}"
        raise TokenUpdateHandlerAPIError(error_msg) from error
