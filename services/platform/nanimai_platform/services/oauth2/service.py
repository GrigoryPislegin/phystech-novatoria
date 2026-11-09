import asyncio
from datetime import UTC, datetime, timedelta
from typing import final

import pydantic
import structlog
from pydantic import BaseModel

from nanimai_platform.domain import OAuth2Profile, Oauth2SourceEnum, Token, UserID
from nanimai_platform.protocols.external.crypt import CryptProtocol
from nanimai_platform.protocols.external.oauth2 import OAuth2APIError, OAuth2Error, OAuth2Protocol, OAuth2ValidateError
from nanimai_platform.protocols.internal import repository as protocol
from nanimai_platform.protocols.internal.repository.oauth2 import OAuth2RepositoryProtocol
from nanimai_platform.protocols.internal.timed_queue import Oauth2TokenQueueError, Oauth2TokenQueueProtocol
from nanimai_platform.services.cache.cache import Cache
from nanimai_platform.services.cache.keyspace import Key, Keyspace
from nanimai_platform.services.crypt import CryptService, CryptServiceError, CryptServiceInvalidDataError
from nanimai_platform.utils import to_utc_timestamp
from nanimai_platform.utils.asyncio_background import launch_background
from nanimai_platform.utils.logging_span import span

log = structlog.stdlib.get_logger("app.service.OAuth2Service")


class OAuth2ServiceError(Exception): ...


class OAuth2ServiceInvalidDataError(Exception): ...


class OAuth2ServiceEmptyTokenError(Exception): ...


class OAuth2ServiceOAuth2NotFoundError(Exception): ...


class OAuth2ServiceUserNotFoundError(Exception): ...


class OAuth2ServiceAPIError(Exception): ...


@final
class OAuth2Service:
    def __init__(
        self,
        oauth2_repo: protocol.OAuth2RepositoryProtocol,
        hh_oauth2_adapter: OAuth2Protocol,
        crypt_x25519_adapter: CryptProtocol,
        cache: Cache,
        token_queue_adapter: Oauth2TokenQueueProtocol,
        crypt_service: CryptService,
    ):
        self._oauth2_repo = oauth2_repo
        self._hh_oauth2_adapter = hh_oauth2_adapter
        self._crypt_x25519_adapter = crypt_x25519_adapter
        self._cache = cache
        self._ks = Keyspace("oauth2_service")
        self._token_queue_adapter = token_queue_adapter
        self._crypt_service = crypt_service
        self._zset_key = "tokens:exp"
        self._min_sleep_sec = 1
        self._max_sleep_sec = 60

    @staticmethod
    def _get_token_id(user_id: UserID, source: Oauth2SourceEnum) -> str:
        return f"{str(user_id)}:{source}"

    class ParseTokenIDResponse(BaseModel):
        user_id: UserID
        source: Oauth2SourceEnum

    @staticmethod
    def _parse_token_id(token_id: str) -> ParseTokenIDResponse:
        user_id, source = token_id.split(":", 1)
        return OAuth2Service.ParseTokenIDResponse(
            user_id=UserID(user_id),
            source=Oauth2SourceEnum(source),
        )

    class GenerateHHLinkRequest(BaseModel):
        redirect_back: str
        user_id: UserID

    def _generate_state(self, request: GenerateHHLinkRequest) -> str:
        try:
            payload = {
                "user_id": str(request.user_id),
                "redirect_back": request.redirect_back,
            }
            state = self._crypt_service.encrypt_dict(
                CryptService.EncryptDictRequest(
                    data=payload,
                )
            )
            return state
        except CryptServiceError as e:
            raise e

    class ParseStateRequest(BaseModel):
        state: str

    class ParseStateResponse(BaseModel):
        redirect_back: str
        user_id: UserID

    def _parse_state(self, request: ParseStateRequest) -> ParseStateResponse:
        try:
            log.debug("Parsing state parameter", state_length=len(request.state) if request.state else 0)
            if not request.state:
                raise CryptServiceInvalidDataError("Empty state parameter")

            parsed_data = self._crypt_service.decrypt_dict(
                CryptService.DecryptDictRequest(
                    data=request.state,
                )
            )
            log.debug("Successfully decrypted state", keys=list(parsed_data.keys()) if parsed_data else [])
            return self.ParseStateResponse(
                redirect_back=parsed_data["redirect_back"],
                user_id=UserID(parsed_data["user_id"]),
            )
        except CryptServiceInvalidDataError as e:
            raise e
        except KeyError as e:
            raise CryptServiceInvalidDataError("missing keys in state") from e
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise CryptServiceInvalidDataError("validation error") from e
        except CryptServiceError as e:
            raise e

    @span(op="oauth2_service", name="generate_hh_link")
    async def generate_hh_link(self, request: GenerateHHLinkRequest) -> OAuth2Protocol.GenerateOAuthLinkResponse:
        try:
            state = self._generate_state(request)

            redirect_url = self._hh_oauth2_adapter.generate_oauth_link(
                OAuth2Protocol.GenerateOAuthLinkRequest(
                    state=state,
                )
            )

            await self._oauth2_repo.create_oauth2_profile(
                OAuth2RepositoryProtocol.CreateOAuth2Request(
                    user_id=request.user_id,
                    source=Oauth2SourceEnum.HH,
                )
            )
            return redirect_url
        except CryptServiceError as e:
            raise e
        except OAuth2Error as e:
            raise OAuth2ServiceAPIError("Failed to generate redirect link") from e
        except protocol.UserNotFoundError as e:
            log.error("failed to find oauth2", err=e)
            raise OAuth2ServiceUserNotFoundError("invalid data") from e
        except protocol.OAuth2ValidateError as e:
            log.error("failed to create oauth2 due to validation error", err=e)
            raise OAuth2ServiceInvalidDataError("invalid data") from e
        except protocol.CreateOAuth2Error as e:
            log.error("failed to create oauth2", err=e)
            raise OAuth2ServiceError("failed to create") from e
        except Exception as e:
            log.error("failed to create oauth2", err=e)
            raise OAuth2ServiceError("unknown error") from e

    class StoreSecretCodeRequest(BaseModel):
        source: Oauth2SourceEnum
        state: str
        secret_code: str

    class StoreSecretCodeResponse(BaseModel):
        redirect_back: str

    @span(op="oauth2_service", name="store_secret_code")
    async def store_secret_code(self, request: StoreSecretCodeRequest) -> StoreSecretCodeResponse:
        try:
            parsed_data = self._parse_state(self.ParseStateRequest(state=request.state))

            log.debug(
                "Received OAuth2 code",
                code_length=len(request.secret_code) if request.secret_code else 0,
                source=request.source,
                state_length=len(request.state) if request.state else 0,
            )

            try:
                new_oauth2 = await self.store_token_by_secret_code(
                    self.StoreTokenBySecretCodeRequest(
                        user_id=parsed_data.user_id,
                        source=request.source,
                        secret_code=request.secret_code,
                    )
                )

                if new_oauth2.token is None:
                    raise OAuth2ServiceError("failed to obtain token by secret code")

                await self._token_queue_adapter.upsert_token(
                    Oauth2TokenQueueProtocol.UpsertTokenRequest(
                        token_id=self._get_token_id(new_oauth2.user_id, new_oauth2.source),
                        expires_at=new_oauth2.token.expires_at,
                        zset_key=self._zset_key,
                    )
                )
                log.info("Successfully processed OAuth2 token")
            except Exception as token_err:
                log.error("Error processing token in store_secret_code", err=token_err)

            return self.StoreSecretCodeResponse(redirect_back=parsed_data.redirect_back)
        except Oauth2TokenQueueError as e:
            log.error("failed to upsert token in queue", err=e)
            raise OAuth2ServiceError("failed to upsert token in queue") from e
        except (CryptServiceInvalidDataError, CryptServiceError) as e:
            raise e
        except Exception as e:
            log.error("failed to store secret code", err=e)
            raise OAuth2ServiceError("unknown error") from e

    class UpdateTokenRequest(BaseModel):
        user_id: UserID
        source: Oauth2SourceEnum
        token: Token

    @span(op="oauth2_service", name="update_token")
    async def update_token(self, request: UpdateTokenRequest) -> OAuth2Profile:
        """Encrypts token and stores to db.
        Do not forget to await self._token_queue_adapter.upsert_token after this
        """
        try:
            encrypted_access_token = self._crypt_x25519_adapter.encrypt(request.token.access_token)
            encrypted_refresh_token = self._crypt_x25519_adapter.encrypt(request.token.refresh_token)
            encrypted_token = Token(
                access_token=encrypted_access_token,
                refresh_token=encrypted_refresh_token,
                expires_in=request.token.expires_in,
                expires_at=request.token.expires_at,
                token_type=request.token.token_type,
            )

            oauth2 = await self._oauth2_repo.update_oauth2_profile(
                OAuth2RepositoryProtocol.UpdateOAuth2Request(
                    user_id=request.user_id,
                    source=request.source,
                    token=encrypted_token,
                )
            )

            if oauth2.token is None:
                raise OAuth2ServiceEmptyTokenError("retrieved token is empty")

            @launch_background
            async def update_cache():
                await self._cache.set(self._oauth2_key(request.user_id, request.source), oauth2)

            update_cache()

            return OAuth2Profile(
                id=oauth2.id,
                created_at=oauth2.created_at,
                updated_at=oauth2.updated_at,
                deleted_at=oauth2.deleted_at,
                user_id=oauth2.user_id,
                source=oauth2.source,
                token=request.token,
            )
        except OAuth2ServiceEmptyTokenError as e:
            log.error("retrieved token is empty", err=e)
            raise e
        except protocol.OAuth2NotFoundError as e:
            log.error("failed to find oauth2", err=e)
            raise OAuth2ServiceOAuth2NotFoundError("invalid data") from e
        except protocol.OAuth2ValidateError as e:
            log.error("failed to store oauth2 secret_code due to validation error", err=e)
            raise OAuth2ServiceInvalidDataError("invalid data") from e
        except protocol.UpdateOAuth2Error as e:
            log.error("failed to update oauth2", err=e)
            raise OAuth2ServiceError("failed to update") from e
        except Exception as e:
            log.error("failed to update oauth2", err=e)
            raise OAuth2ServiceError("unknown error") from e

    class StoreTokenRequest(BaseModel):
        user_id: UserID
        source: Oauth2SourceEnum
        token: Token

    @span(op="oauth2_service", name="store_token")
    async def store_token(self, request: StoreTokenRequest) -> OAuth2Profile:
        """Encrypts token and stores to db.
        Do not forget to await self._token_queue_adapter.upsert_token after this
        """
        try:
            encrypted_access_token = self._crypt_x25519_adapter.encrypt(request.token.access_token)
            encrypted_refresh_token = self._crypt_x25519_adapter.encrypt(request.token.refresh_token)
            encrypted_token = Token(
                access_token=encrypted_access_token,
                refresh_token=encrypted_refresh_token,
                expires_in=request.token.expires_in,
                expires_at=request.token.expires_at,
                token_type=request.token.token_type,
            )

            oauth2 = await self._oauth2_repo.create_oauth2_profile(
                OAuth2RepositoryProtocol.CreateOAuth2Request(
                    user_id=request.user_id,
                    source=request.source,
                    token=encrypted_token,
                )
            )

            if oauth2.token is None:
                raise OAuth2ServiceEmptyTokenError("retrieved token is empty")

            @launch_background
            async def update_cache():
                await self._cache.set(self._oauth2_key(request.user_id, request.source), oauth2)

            update_cache()

            return OAuth2Profile(
                id=oauth2.id,
                created_at=oauth2.created_at,
                updated_at=oauth2.updated_at,
                deleted_at=oauth2.deleted_at,
                user_id=oauth2.user_id,
                source=oauth2.source,
                token=request.token,
            )
        except OAuth2ServiceEmptyTokenError as e:
            log.error("retrieved token is empty", err=e)
            raise e
        except protocol.OAuth2NotFoundError as e:
            log.error("failed to find oauth2", err=e)
            raise OAuth2ServiceOAuth2NotFoundError("invalid data") from e
        except protocol.OAuth2ValidateError as e:
            log.error("failed to store oauth2 secret_code due to validation error", err=e)
            raise OAuth2ServiceInvalidDataError("invalid data") from e
        except protocol.UpdateOAuth2Error as e:
            log.error("failed to update oauth2", err=e)
            raise OAuth2ServiceError("failed to update") from e
        except Exception as e:
            log.error("failed to update oauth2", err=e)
            raise OAuth2ServiceError("unknown error") from e

    class StoreTokenBySecretCodeRequest(BaseModel):
        user_id: UserID
        source: Oauth2SourceEnum
        secret_code: str

    @span(op="oauth2_service", name="store_token_by_secret_code")
    async def store_token_by_secret_code(self, request: StoreTokenBySecretCodeRequest) -> OAuth2Profile:
        try:
            log.debug(
                "Attempting to exchange code for token",
                source=request.source,
                code_length=len(request.secret_code) if request.secret_code else 0,
            )

            if request.source == Oauth2SourceEnum.HH:
                response = await self._hh_oauth2_adapter.get_token_by_secret_code(
                    OAuth2Protocol.GetTokensBySecretCodeRequest(
                        secret_code=request.secret_code,
                    )
                )
            else:
                raise OAuth2ServiceError("not implemented source")

            oauth2 = await self.update_token(
                self.UpdateTokenRequest(
                    user_id=request.user_id,
                    source=request.source,
                    token=response.token,
                )
            )
            log.info("Successfully stored OAuth2 token in database")

            return oauth2

        except OAuth2ServiceError as e:
            log.error("service for source is not implemented", err=e)
            raise e
        except OAuth2ValidateError as e:
            log.error(
                "failed to get token by secret code via api (validation)",
                err=e,
                secret_code_length=len(request.secret_code) if request.secret_code else 0,
            )
            raise OAuth2ServiceAPIError(f"failed to validate api response: {str(e)}") from e
        except OAuth2APIError as e:
            log.error(
                "failed to get token by secret code via api (api)",
                err=e,
                error_details=str(e),
                source=request.source,
                secret_code_length=len(request.secret_code) if request.secret_code else 0,
            )
            raise OAuth2ServiceAPIError(f"failed to send request to api: {str(e)}") from e
        except OAuth2Error as e:
            log.error("failed to get token by secret code via api", err=e)
            raise OAuth2ServiceAPIError("unknown error") from e
        except (OAuth2ServiceEmptyTokenError, OAuth2ServiceOAuth2NotFoundError, OAuth2ServiceInvalidDataError) as e:
            raise e
        except Exception as e:
            log.error("failed to store token by secret code", err=e)
            raise OAuth2ServiceError("unknown error") from e

    class RetrieveTokenRequest(BaseModel):
        user_id: UserID
        source: Oauth2SourceEnum

    @span(op="oauth2_service", name="retrieve_token")
    async def retrieve_token(self, request: RetrieveTokenRequest) -> OAuth2Profile:
        try:
            if (
                oauth2 := await self._cache.get(self._oauth2_key(request.user_id, request.source), t=OAuth2Profile)
            ) is None:
                oauth2 = await self._oauth2_repo.read_oauth2_profile(
                    OAuth2RepositoryProtocol.ReadOAuth2Request(
                        user_id=request.user_id,
                        source=request.source,
                    )
                )

                @launch_background
                async def update_cache():
                    await self._cache.set(self._oauth2_key(request.user_id, request.source), oauth2)

                update_cache()

            if oauth2.token is None:
                raise OAuth2ServiceEmptyTokenError("retrieved token is empty")

            decrypted_access_token = self._crypt_x25519_adapter.decrypt(oauth2.token.access_token)
            decrypted_refresh_token = self._crypt_x25519_adapter.decrypt(oauth2.token.refresh_token)
            decrypted_token = Token(
                access_token=decrypted_access_token,
                refresh_token=decrypted_refresh_token,
                expires_in=oauth2.token.expires_in,
                expires_at=oauth2.token.expires_at,
                token_type=oauth2.token.token_type,
            )

            return OAuth2Profile(
                id=oauth2.id,
                created_at=oauth2.created_at,
                updated_at=oauth2.updated_at,
                deleted_at=oauth2.deleted_at,
                user_id=oauth2.user_id,
                source=oauth2.source,
                token=decrypted_token,
            )
        except protocol.OAuth2NotFoundError as e:
            log.error("failed to find oauth2", err=e)
            raise OAuth2ServiceOAuth2NotFoundError("invalid data") from e
        except OAuth2ServiceEmptyTokenError as e:
            log.error("retrieved token is empty", err=e)
            raise e
        except protocol.OAuth2ValidateError as e:
            log.error("failed to retrieve token due to validation error", err=e)
            raise OAuth2ServiceInvalidDataError("invalid data") from e
        except protocol.ReadOAuth2Error as e:
            log.error("failed to read oauth2", err=e)
            raise OAuth2ServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to retrieve oauth2 tokens", err=e)
            raise OAuth2ServiceError("unknown error") from e

    class RenewTokenRequest(BaseModel):
        user_id: UserID
        source: Oauth2SourceEnum

    @span(op="oauth2_service", name="renew_token")
    async def renew_token(self, request: RenewTokenRequest) -> OAuth2Profile:  # noqa: C901
        try:
            oauth2 = await self.retrieve_token(
                self.RetrieveTokenRequest(
                    user_id=request.user_id,
                    source=request.source,
                )
            )

            if oauth2.token is None:
                raise OAuth2ServiceEmptyTokenError("token not found")

            if request.source == Oauth2SourceEnum.HH:
                response = await self._hh_oauth2_adapter.refresh_tokens(
                    OAuth2Protocol.RefreshTokensRequest(
                        refresh_token=oauth2.token.refresh_token,
                    )
                )
            else:
                raise OAuth2ServiceError("not implemented source")

            decrypted_token = Token(
                access_token=response.token.access_token,
                refresh_token=response.token.refresh_token,
                expires_in=response.token.expires_in,
                expires_at=response.token.expires_at,
                token_type=response.token.token_type,
            )

            response = await self.update_token(
                self.UpdateTokenRequest(
                    user_id=request.user_id,
                    source=request.source,
                    token=decrypted_token,
                )
            )

            if response.token is None:
                raise OAuth2ServiceEmptyTokenError("token not found")

            await self._token_queue_adapter.upsert_token(
                Oauth2TokenQueueProtocol.UpsertTokenRequest(
                    token_id=self._get_token_id(response.user_id, response.source),
                    expires_at=response.token.expires_at,
                    zset_key=self._zset_key,
                )
            )
            return response
        except Oauth2TokenQueueError as e:
            log.error("failed to upsert token in queue", err=e)
            raise e
        except (OAuth2ServiceEmptyTokenError, OAuth2ServiceOAuth2NotFoundError, OAuth2ServiceInvalidDataError) as e:
            raise e
        except OAuth2ServiceError as e:
            log.error("service for source is not implemented", err=e)
            raise e
        except protocol.OAuth2NotFoundError as e:
            log.error("failed to find oauth2", err=e)
            raise OAuth2ServiceOAuth2NotFoundError("invalid data") from e
        except protocol.OAuth2ValidateError as e:
            log.error("failed to read oauth2 due to validation error", err=e)
            raise OAuth2ServiceInvalidDataError("invalid data") from e
        except protocol.ReadOAuth2Error as e:
            log.error("failed to read oauth2", err=e)
            raise OAuth2ServiceError("failed to read") from e
        except protocol.UpdateOAuth2Error as e:
            log.error("failed to update oauth2", err=e)
            raise OAuth2ServiceError("failed to update") from e
        except Exception as e:
            log.error("failed to renew oauth2 tokens", err=e)
            raise OAuth2ServiceError("unknown error") from e

    class GetActiveIntegrationsRequest(BaseModel):
        user_id: UserID

    class GetActiveIntegrationsResponse(BaseModel):
        active_integrations: dict[Oauth2SourceEnum, bool]

    @span(op="oauth2_service", name="get_active_integrations")
    async def get_active_integrations(self, request: GetActiveIntegrationsRequest) -> GetActiveIntegrationsResponse:
        try:
            active_integrations = {source: False for source in Oauth2SourceEnum}
            oauth2_profiles = await self._oauth2_repo.read_many_oauth2_profiles(
                OAuth2RepositoryProtocol.ReadManyOAuth2Request(user_id=request.user_id)
            )
            for oauth2_profile in oauth2_profiles:
                active_integrations[oauth2_profile.source] = True
            return self.GetActiveIntegrationsResponse(active_integrations=active_integrations)
        except protocol.OAuth2ValidateError as e:
            log.error("failed to get active integrations due to validation error", err=e)
            raise OAuth2ServiceInvalidDataError("invalid data") from e
        except protocol.ReadOAuth2Error as e:
            log.error("failed to read oauth2", err=e)
            raise OAuth2ServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to get active integrations", err=e)
            raise OAuth2ServiceError("unknown error") from e

    @span(op="oauth2_service", name="run_worker")
    async def run_worker(self):  # noqa: C901
        try:
            log.info("retrieving token")
            while True:
                response = await self._token_queue_adapter.read_earliest_token(
                    Oauth2TokenQueueProtocol.ReadEarliestTokenRequest(
                        zset_key=self._zset_key,
                    )
                )
                if response:
                    parsed_token_id = self._parse_token_id(response.token_id)
                    user_id = parsed_token_id.user_id
                    source = parsed_token_id.source

                    log.info("last retrieved token", user_id=user_id, source=source)

                    retrieved_expires_at = response.expires_at
                    if retrieved_expires_at <= datetime.now(UTC):
                        oauth2 = await self.renew_token(
                            self.RenewTokenRequest(
                                user_id=user_id,
                                source=source,
                            )
                        )

                        if oauth2.token is None:
                            raise OAuth2ServiceEmptyTokenError("token not found")

                        await self._token_queue_adapter.upsert_token(
                            Oauth2TokenQueueProtocol.UpsertTokenRequest(
                                token_id=response.token_id,
                                expires_at=oauth2.token.expires_at,
                                zset_key=self._zset_key,
                            )
                        )
                        log.info("token updated", user_id=user_id, source=source)
                    else:
                        next_expires_at = retrieved_expires_at
                        break
                else:
                    next_expires_at = datetime.now(UTC) + timedelta(minutes=2)
                    break

            now = datetime.now(UTC)
            sleep_datetime = max(
                now + timedelta(seconds=self._min_sleep_sec),
                min(next_expires_at, now + timedelta(seconds=self._max_sleep_sec)),
            )
            sleep_time = to_utc_timestamp(sleep_datetime) - to_utc_timestamp(now)
            log.info(f"waiting for {sleep_time} seconds")
            await asyncio.sleep(sleep_time)
        except OAuth2ServiceEmptyTokenError as e:
            log.error("retrieved token is empty", err=e)
            raise e
        except OAuth2ServiceError as e:
            log.error("service for source is not implemented", err=e)
            raise e
        except protocol.OAuth2NotFoundError as e:
            log.error("failed to find oauth2", err=e)
            raise OAuth2ServiceOAuth2NotFoundError("invalid data") from e
        except protocol.OAuth2ValidateError as e:
            log.error("failed to read oauth2 due to validation error", err=e)
            raise OAuth2ServiceInvalidDataError("invalid data") from e
        except protocol.ReadOAuth2Error as e:
            log.error("failed to read oauth2", err=e)
            raise OAuth2ServiceError("failed to read") from e
        except protocol.UpdateOAuth2Error as e:
            log.error("failed to update oauth2", err=e)
            raise OAuth2ServiceError("failed to update") from e
        except Oauth2TokenQueueError as e:
            log.error("failed to create, read or update in queue", err=e)
            raise OAuth2ServiceError("failed to deal with queue") from e
        except Exception as e:
            log.error("failed to renew oauth2 tokens", err=e)
            raise OAuth2ServiceError("unknown error") from e

    # ===

    def _oauth2_key(self, user_id: UserID, source: Oauth2SourceEnum) -> Key:
        return self._ks.key("id", f"{str(user_id)}_{str(source)}")
