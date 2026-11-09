from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import final

import pydantic
import structlog

from hharon.domain.token import TokenPair
from hharon.protocols import cache as cache_protocol
from hharon.protocols import oauth2 as oauth2_protocol
from hharon.protocols import token as token_protocol
from hharon.protocols import user as user_protocol
from hharon.protocols.outbox_task import OutboxContext
from hharon.usecases.crypt import CipherUsecase, CipherUsecaseEncryptError
from hharon.usecases.oauth2.state import EncryptOAuthState, EncryptOAuthStateDecryptError
from hharon.usecases.oauth2.token import ExchangeSecretCode, ExchangeSecretCodeError
from hharon.usecases.outbox_task.schedulers.token_update_scheduler import TokenUpdateScheduler

log = structlog.stdlib.get_logger("hharon.usecases.oauth2.flow.CompleteOauthFlow")


class CompleteOauthFlowError(Exception):
    """Base exception class for CompleteOauthFlow errors."""


class CompleteOauthFlowDecryptError(CompleteOauthFlowError):
    """Decryption error raised by CompleteOauthFlow."""


class CompleteOauthFlowExchangeError(CompleteOauthFlowError):
    """Exchange secret code error raised by CompleteOauthFlow."""


class CompleteOauthFlowUserInfoError(CompleteOauthFlowError):
    """User info error raised by CompleteOauthFlow."""


class CompleteOauthFlowSaveUserError(CompleteOauthFlowError):
    """Save user error raised by CompleteOauthFlow."""


class CompleteOauthFlowSaveTokensError(CompleteOauthFlowError):
    """Save tokens error raised by CompleteOauthFlow."""


class CompleteOauthFlowEncryptError(CompleteOauthFlowError):
    """Encryption error raised by CompleteOauthFlow."""


class CompleteOauthFlowScheduleError(CompleteOauthFlowError):
    """Schedule task error raised by CompleteOauthFlow."""


@final
class CompleteOauthFlow[SessionT]:
    _USER_CACHE_KEY_PREFIX = "hharon:user:"

    def __init__(  # noqa: PLR0913
        self,
        *,
        exchange_secret_code_usecase: ExchangeSecretCode,
        hh_user_info_adapter: oauth2_protocol.OAuth2UserInfoProtocol,
        encrypt_state_usecase: EncryptOAuthState,
        user_repository: user_protocol.HharonUserRepositoryProtocol[SessionT],
        token_repository: token_protocol.HeadHunterTokenRepositoryProtocol[SessionT],
        cipher_usecase: CipherUsecase,
        token_update_scheduler: TokenUpdateScheduler[SessionT],
        cache: cache_protocol.CacheProtocol,
    ) -> None:
        self._exchange_secret_code_usecase = exchange_secret_code_usecase
        self._hh_user_info_adapter = hh_user_info_adapter
        self._encrypt_state_usecase = encrypt_state_usecase
        self._user_repository = user_repository
        self._token_repository = token_repository
        self._cipher_usecase = cipher_usecase
        self._token_update_scheduler = token_update_scheduler
        self._cache = cache

    class CompleteOauthFlowRequest(pydantic.BaseModel):
        """Request to complete OAuth flow."""

        secret_code: str
        encrypted_state: str
        redirect_uri: str

    class CompleteOauthFlowResponse(pydantic.BaseModel):
        """Response after completing OAuth flow."""

        success: bool = True
        user_id: str

    @pydantic.dataclasses.dataclass
    class _SaveUserAndTokensRequest:
        """Request to save user and tokens."""

        user_id: str
        hh_manager_id: str
        hh_employer_id: str
        name: str
        email: str
        access_token: str
        refresh_token: str
        expires_in: int

    async def _save_user_and_tokens(
        self,
        *,
        session: SessionT,
        request: _SaveUserAndTokensRequest,
    ) -> tuple[str, bool, TokenPair]:

        existing_user = await self._user_repository.get_user(
            session,
            user_protocol.HharonUserRepositoryProtocol.GetUserRequest(user_id=request.user_id),
        )

        if existing_user is not None:
            # Re-authorization: update user with new HH data
            log.debug(
                "Updating existing user (re-auth)",
                user_id=existing_user.user_id,
                hh_manager_id=request.hh_manager_id,
            )
            hharon_user = await self._user_repository.update_user(
                session,
                user_protocol.HharonUserRepositoryProtocol.UpdateUserRequest(
                    user_id=existing_user.user_id,
                    name=request.name,
                    email=request.email,
                    hh_manager_id=request.hh_manager_id,
                    hh_employer_id=request.hh_employer_id,
                ),
            )
            is_reauth = True
        else:
            existing_user = await self._user_repository.get_user_by_hh_manager_id(
                session,
                user_protocol.HharonUserRepositoryProtocol.GetUserByHhIdRequest(hh_manager_id=request.hh_manager_id),
            )

            if existing_user is not None:
                log.debug(
                    "Updating existing user",
                    user_id=existing_user.user_id,
                    hh_manager_id=request.hh_manager_id,
                )
                hharon_user = await self._user_repository.update_user(
                    session,
                    user_protocol.HharonUserRepositoryProtocol.UpdateUserRequest(
                        user_id=existing_user.user_id,
                        name=request.name,
                        email=request.email,
                    ),
                )
                is_reauth = True
            else:
                log.debug(
                    "Creating new user",
                    user_id=request.user_id,
                    hh_manager_id=request.hh_manager_id,
                )
                hharon_user = await self._user_repository.create_user(
                    session,
                    user_protocol.HharonUserRepositoryProtocol.CreateUserRequest(
                        user_id=request.user_id,
                        hh_manager_id=request.hh_manager_id,
                        hh_employer_id=request.hh_employer_id,
                        name=request.name,
                        email=request.email,
                    ),
                )
                is_reauth = False

        log.info(
            "Successfully saved user",
            user_id=hharon_user.user_id,
            hh_manager_id=request.hh_manager_id,
        )

        # Encrypt tokens
        log.debug("Encrypting and saving tokens", user_id=hharon_user.user_id)
        encrypt_access_response = self._cipher_usecase.encrypt_bytes(
            CipherUsecase.EncryptBytesRequest(data=request.access_token.encode("utf-8"))
        )
        encrypt_refresh_response = self._cipher_usecase.encrypt_bytes(
            CipherUsecase.EncryptBytesRequest(data=request.refresh_token.encode("utf-8"))
        )
        expires_at = datetime.now(UTC) + timedelta(seconds=request.expires_in)

        # Token upsert: update if re-auth, save if new user
        if is_reauth:
            token_pair = await self._token_repository.update_tokens(
                session,
                token_protocol.HeadHunterTokenRepositoryProtocol.UpdateTokensRequest(
                    user_id=hharon_user.user_id,
                    encrypted_access_token=encrypt_access_response.data,
                    encrypted_refresh_token=encrypt_refresh_response.data,
                    expires_at=expires_at,
                    token_type="bearer",  # noqa: S106
                    is_invalid=False,
                ),
            )
            log.info(
                "Successfully updated tokens (re-auth)",
                user_id=hharon_user.user_id,
                expires_at=expires_at,
            )
        else:
            token_pair = await self._token_repository.save_tokens(
                session,
                token_protocol.HeadHunterTokenRepositoryProtocol.SaveTokensRequest(
                    user_id=hharon_user.user_id,
                    encrypted_access_token=encrypt_access_response.data,
                    encrypted_refresh_token=encrypt_refresh_response.data,
                    expires_at=expires_at,
                    token_type="bearer",  # noqa: S106
                ),
            )
            log.info(
                "Successfully saved tokens",
                user_id=hharon_user.user_id,
                expires_at=expires_at,
            )

        return hharon_user.user_id, is_reauth, token_pair

    async def _schedule_token_refresh_task(
        self,
        *,
        session: SessionT,
        user_id: str,
        expires_in: int,
    ) -> None:
        """Schedule token refresh task in outbox using the provided session."""
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        log.debug("Scheduling token refresh task", user_id=user_id, expires_at=expires_at)
        try:
            ctx = OutboxContext[SessionT](session=session)
            await self._token_update_scheduler.schedule(
                ctx=ctx,
                user_id=user_id,
                expires_at=expires_at,
            )
            log.info("Successfully scheduled token refresh task", user_id=user_id, expires_at=expires_at)
        except Exception as e:
            log.exception("Failed to schedule token refresh task", user_id=user_id)
            raise CompleteOauthFlowScheduleError("failed to schedule token refresh") from e

    @dataclass(frozen=True)
    class _OAuthFlowData:
        """Data collected during OAuth flow steps 1-3."""

        user_id: str
        hh_manager_id: str
        hh_employer_id: str
        name: str
        email: str
        access_token: str
        refresh_token: str
        expires_in: int

    async def _collect_oauth_data(self, request: CompleteOauthFlowRequest) -> _OAuthFlowData:
        """Collect OAuth data: decrypt state, exchange code, get user info."""
        # 1. Decrypt state to get user_id
        log.debug(
            "Decrypting OAuth state",
            state_length=len(request.encrypted_state) if request.encrypted_state else 0,
        )
        decrypted_state = self._encrypt_state_usecase.decrypt_oauth_state(
            EncryptOAuthState.DecryptOAuthStateRequest(state=request.encrypted_state)
        )
        log.debug("Successfully decrypted state", user_id=decrypted_state.user_id)

        # 2. Exchange secret code for tokens
        log.debug(
            "Exchanging secret code for tokens",
            code_length=len(request.secret_code) if request.secret_code else 0,
            user_id=decrypted_state.user_id,
        )
        token_response = await self._exchange_secret_code_usecase.exchange_secret_code(
            ExchangeSecretCode.ExchangeSecretCodeRequest(
                secret_code=request.secret_code,
                encrypted_state=request.encrypted_state,
                redirect_uri=request.redirect_uri,
            )
        )
        log.debug("Successfully exchanged code for tokens", user_id=decrypted_state.user_id)

        # 3. Get user info from HeadHunter
        log.debug("Getting user info from HeadHunter", user_id=decrypted_state.user_id)
        user_info_response = await self._hh_user_info_adapter.get_current_user_info(
            oauth2_protocol.OAuth2UserInfoProtocol.GetCurrentUserInfoRequest(
                access_token=token_response.access_token,
            )
        )
        log.debug(
            "Successfully got user info",
            user_id=decrypted_state.user_id,
            hh_manager_id=user_info_response.hh_manager_id,
        )

        return self._OAuthFlowData(
            user_id=decrypted_state.user_id,
            hh_manager_id=user_info_response.hh_manager_id,
            hh_employer_id=user_info_response.hh_employer_id,
            name=user_info_response.name,
            email=user_info_response.email,
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            expires_in=token_response.expires_in,
        )

    async def _save_user_tokens_and_schedule(self, *, oauth_data: _OAuthFlowData) -> str:
        """Save user, tokens and schedule refresh task in the same transaction."""
        async with self._user_repository.context() as session:
            try:
                user_id, is_reauth, _ = await self._save_user_and_tokens(
                    session=session,
                    request=self._SaveUserAndTokensRequest(
                        user_id=oauth_data.user_id,
                        hh_manager_id=oauth_data.hh_manager_id,
                        hh_employer_id=oauth_data.hh_employer_id,
                        name=oauth_data.name,
                        email=oauth_data.email,
                        access_token=oauth_data.access_token,
                        refresh_token=oauth_data.refresh_token,
                        expires_in=oauth_data.expires_in,
                    ),
                )
                if is_reauth:
                    ctx = OutboxContext[SessionT](session=session)
                    _ = await self._token_update_scheduler.cancel_pending_for_user(ctx=ctx, user_id=user_id)
                # Schedule token refresh task in the same transaction
                await self._schedule_token_refresh_task(
                    session=session,
                    user_id=user_id,
                    expires_in=oauth_data.expires_in,
                )
            except CipherUsecaseEncryptError as e:
                log.exception("failed to encrypt tokens")
                raise CompleteOauthFlowEncryptError("failed to encrypt tokens") from e
            except token_protocol.HeadHunterTokenRepositoryError as e:
                log.exception("failed to save tokens")
                raise CompleteOauthFlowSaveTokensError("failed to save tokens") from e
            except CompleteOauthFlowScheduleError:
                raise
            else:
                return user_id

    async def complete_oauth_flow(self, request: CompleteOauthFlowRequest) -> CompleteOauthFlowResponse:
        """Complete OAuth2 flow: exchange code, get user info, save user and tokens, schedule refresh."""
        try:
            oauth_data = await self._collect_oauth_data(request=request)
            user_id = await self._save_user_tokens_and_schedule(oauth_data=oauth_data)

            await self._cache.delete(f"{self._USER_CACHE_KEY_PREFIX}{user_id}")

            return self.CompleteOauthFlowResponse(success=True, user_id=user_id)

        except EncryptOAuthStateDecryptError as e:
            log.exception("failed to decrypt oauth state")
            raise CompleteOauthFlowDecryptError("failed to decrypt state") from e
        except ExchangeSecretCodeError as e:
            log.exception("failed to exchange secret code")
            raise CompleteOauthFlowExchangeError("failed to exchange secret code") from e
        except oauth2_protocol.OAuth2Error as e:
            log.exception("failed to get user info from HeadHunter")
            raise CompleteOauthFlowUserInfoError("failed to get user info") from e
        except CompleteOauthFlowEncryptError:
            log.exception("failed to encrypt tokens")
            raise
        except CompleteOauthFlowSaveTokensError:
            log.exception("failed to save tokens")
            raise
        except CompleteOauthFlowScheduleError:
            raise
        except Exception as e:
            log.exception("unexpected error in complete oauth flow")
            raise CompleteOauthFlowError("unexpected error") from e
