from datetime import UTC, datetime, timedelta
from typing import final

import pydantic
import structlog

from hharon.domain.token import TokenPair
from hharon.protocols import oauth2 as oauth2_protocol
from hharon.protocols import token as token_protocol
from hharon.protocols.outbox_task import OutboxContext
from hharon.usecases.crypt import CipherUsecase, CipherUsecaseDecryptError, CipherUsecaseEncryptError
from hharon.usecases.outbox_task.schedulers.token_update_scheduler import TokenUpdateScheduler

log = structlog.stdlib.get_logger("hharon.usecases.token.RefreshTokens")


class RefreshTokensError(Exception):
    """Base exception class for RefreshTokens errors."""


class RefreshTokensNotFoundError(RefreshTokensError):
    """Tokens not found error."""


class RefreshTokensDecryptError(RefreshTokensError):
    """Decryption error raised by RefreshTokens."""


class RefreshTokensEncryptError(RefreshTokensError):
    """Encryption error raised by RefreshTokens."""


class RefreshTokensAPIError(RefreshTokensError):
    """API error raised by RefreshTokens."""


class RefreshTokensScheduleError(RefreshTokensError):
    """Schedule task error raised by RefreshTokens."""


@final
class RefreshTokens[SessionT]:
    def __init__(
        self,
        *,
        token_repository: token_protocol.HeadHunterTokenRepositoryProtocol[SessionT],
        hh_oauth2_adapter: oauth2_protocol.OAuth2Protocol,
        cipher_usecase: CipherUsecase,
        token_update_scheduler: TokenUpdateScheduler[SessionT],
    ) -> None:
        self._token_repository = token_repository
        self._hh_oauth2_adapter = hh_oauth2_adapter
        self._cipher_usecase = cipher_usecase
        self._token_update_scheduler = token_update_scheduler

    class RefreshTokensRequest(pydantic.BaseModel):
        """Request to refresh tokens."""

        user_id: str

    class RefreshTokensResponse(pydantic.BaseModel):
        """Response with refreshed tokens."""

        access_token: str
        refresh_token: str
        expires_in: int

    async def refresh_and_update_tokens(
        self, *, session: SessionT, token_pair: TokenPair, user_id: str
    ) -> oauth2_protocol.OAuth2Protocol.TokenResponse:
        """Refresh tokens via OAuth2 API and update them in repository."""
        log.debug("Decrypting refresh token", user_id=user_id)
        decrypt_refresh_response = self._cipher_usecase.decrypt_bytes(
            CipherUsecase.DecryptBytesRequest(data=token_pair.encrypted_refresh_token)
        )
        refresh_token = decrypt_refresh_response.data.decode("utf-8")

        log.debug("Refreshing tokens via OAuth2 API", user_id=user_id)
        token_response = await self._hh_oauth2_adapter.refresh_tokens(
            oauth2_protocol.OAuth2Protocol.RefreshTokensRequest(refresh_token=refresh_token)
        )

        log.debug("Encrypting new tokens", user_id=user_id)
        encrypt_access_response = self._cipher_usecase.encrypt_bytes(
            CipherUsecase.EncryptBytesRequest(data=token_response.token.access_token.encode("utf-8"))
        )
        encrypted_access_token = encrypt_access_response.data

        encrypt_refresh_response = self._cipher_usecase.encrypt_bytes(
            CipherUsecase.EncryptBytesRequest(data=token_response.token.refresh_token.encode("utf-8"))
        )
        encrypted_refresh_token = encrypt_refresh_response.data

        expires_at = datetime.now(UTC) + timedelta(seconds=token_response.token.expires_in)

        log.debug("Updating tokens in repository", user_id=user_id)
        _ = await self._token_repository.update_tokens(
            session,
            token_protocol.HeadHunterTokenRepositoryProtocol.UpdateTokensRequest(
                user_id=user_id,
                encrypted_access_token=encrypted_access_token,
                encrypted_refresh_token=encrypted_refresh_token,
                expires_at=expires_at,
                token_type=token_response.token.token_type,
                is_invalid=False,
            ),
        )

        return token_response

    async def _schedule_token_refresh_task(
        self,
        *,
        session: SessionT,
        user_id: str,
        expires_at: datetime,
    ) -> None:
        """Schedule token refresh task in outbox using the provided session."""
        log.debug("Scheduling next token refresh task", user_id=user_id, expires_at=expires_at)
        try:
            ctx = OutboxContext[SessionT](session=session)
            await self._token_update_scheduler.schedule(
                ctx=ctx,
                user_id=user_id,
                expires_at=expires_at,
            )
            log.info(
                "Successfully scheduled next token refresh task",
                user_id=user_id,
                expires_at=expires_at,
            )
        except Exception as e:
            log.exception("failed to schedule next token refresh task", user_id=user_id)
            error_msg = f"failed to schedule next token refresh task: {e!s}"
            raise RefreshTokensScheduleError(error_msg) from e

    async def refresh_tokens(self, request: RefreshTokensRequest) -> RefreshTokensResponse:
        """Refresh tokens using refresh_token from repository."""
        try:
            log.debug("Refreshing tokens", user_id=request.user_id)

            # Get tokens with lock for update
            async with self._token_repository.context() as session:
                token_pair = await self._token_repository.lock_tokens_for_update(
                    session,
                    token_protocol.HeadHunterTokenRepositoryProtocol.LockTokensRequest(user_id=request.user_id),
                )

                if token_pair is None:
                    log.warning("Tokens not found", user_id=request.user_id)
                    error_msg = f"Tokens not found for user_id: {request.user_id}"
                    raise RefreshTokensNotFoundError(error_msg)

                if token_pair.is_invalid:
                    log.warning("Tokens are marked as invalid", user_id=request.user_id)
                    error_msg = f"Tokens are invalid for user_id: {request.user_id}"
                    raise RefreshTokensNotFoundError(error_msg)

                token_response = await self.refresh_and_update_tokens(
                    session=session, token_pair=token_pair, user_id=request.user_id
                )

                expires_at = datetime.now(UTC) + timedelta(seconds=token_response.token.expires_in)
                await self._schedule_token_refresh_task(
                    session=session,
                    user_id=request.user_id,
                    expires_at=expires_at,
                )

            log.info("Successfully refreshed tokens", user_id=request.user_id)

            return self.RefreshTokensResponse(
                access_token=token_response.token.access_token,
                refresh_token=token_response.token.refresh_token,
                expires_in=token_response.token.expires_in,
            )
        except RefreshTokensNotFoundError:
            raise
        except CipherUsecaseDecryptError as e:
            log.exception("failed to decrypt refresh token", user_id=request.user_id)
            raise RefreshTokensDecryptError("failed to decrypt refresh token") from e
        except CipherUsecaseEncryptError as e:
            log.exception("failed to encrypt new tokens", user_id=request.user_id)
            raise RefreshTokensEncryptError("failed to encrypt new tokens") from e
        except oauth2_protocol.OAuth2APIError as e:
            log.exception("failed to refresh tokens via API", user_id=request.user_id)
            # Mark tokens as invalid on API error
            async with self._token_repository.context() as session:
                _ = await self._token_repository.mark_tokens_invalid(
                    session,
                    token_protocol.HeadHunterTokenRepositoryProtocol.MarkTokensInvalidRequest(
                        user_id=request.user_id,
                    ),
                )
            error_msg = f"failed to refresh tokens via API: {e!s}"
            raise RefreshTokensAPIError(error_msg) from e
        except oauth2_protocol.OAuth2Error as e:
            log.exception("failed to refresh tokens", user_id=request.user_id)
            error_msg = f"failed to refresh tokens: {e!s}"
            raise RefreshTokensAPIError(error_msg) from e
        except RefreshTokensScheduleError:
            log.exception("failed to schedule next token refresh task", user_id=request.user_id)
            raise
        except Exception as e:
            log.exception("unexpected error in refresh tokens", user_id=request.user_id)
            raise RefreshTokensError("unexpected error") from e
