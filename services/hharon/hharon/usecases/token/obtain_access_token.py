from typing import final

import pydantic
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.protocols import token as token_protocol
from hharon.usecases.crypt import CipherUsecase, CipherUsecaseDecryptError

log = structlog.stdlib.get_logger("hharon.usecases.token.ObtainAccessToken")


class ObtainAccessTokenError(Exception):
    """Base exception class for ObtainAccessToken errors."""


class ObtainAccessTokenNotFoundError(ObtainAccessTokenError):
    """Tokens not found error."""


class ObtainAccessTokenInvalidError(ObtainAccessTokenError):
    """Tokens are invalid error."""


class ObtainAccessTokenDecryptError(ObtainAccessTokenError):
    """Decryption error raised by ObtainAccessToken."""


@final
class ObtainAccessToken:
    def __init__(
        self,
        *,
        token_repository: token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession],
        cipher_usecase: CipherUsecase,
    ) -> None:
        self._token_repository = token_repository
        self._cipher_usecase = cipher_usecase

    class ObtainAccessTokenRequest(pydantic.BaseModel):
        """Request to obtain access token."""

        user_id: str

    class ObtainAccessTokenResponse(pydantic.BaseModel):
        """Response with access token."""

        access_token: str

    async def obtain_access_token(self, request: ObtainAccessTokenRequest) -> ObtainAccessTokenResponse:
        """Obtain access token from repository, waiting for lock release if tokens are being refreshed."""
        try:
            log.debug("Obtaining access token", user_id=request.user_id)

            # Get tokens with lock for update - this will wait if tokens are being refreshed
            async with self._token_repository.context() as session:
                token_pair = await self._token_repository.lock_tokens_for_update(
                    session,
                    token_protocol.HeadHunterTokenRepositoryProtocol.LockTokensRequest(user_id=request.user_id),
                )

                if token_pair is None:
                    log.warning("Tokens not found", user_id=request.user_id)
                    error_msg = f"Tokens not found for user_id: {request.user_id}"
                    raise ObtainAccessTokenNotFoundError(error_msg)

                if token_pair.is_invalid:
                    log.warning("Tokens are marked as invalid", user_id=request.user_id)
                    error_msg = f"Tokens are invalid for user_id: {request.user_id}"
                    raise ObtainAccessTokenInvalidError(error_msg)

                log.debug("Decrypting access token", user_id=request.user_id)

                # Decrypt access token
                decrypt_access_response = self._cipher_usecase.decrypt_bytes(
                    CipherUsecase.DecryptBytesRequest(data=token_pair.encrypted_access_token)
                )
                access_token = decrypt_access_response.data.decode("utf-8")

                log.info("Successfully obtained access token", user_id=request.user_id)

                return self.ObtainAccessTokenResponse(access_token=access_token)
        except ObtainAccessTokenNotFoundError:
            raise
        except ObtainAccessTokenInvalidError:
            raise
        except CipherUsecaseDecryptError as e:
            log.exception("failed to decrypt access token", user_id=request.user_id)
            raise ObtainAccessTokenDecryptError("failed to decrypt access token") from e
        except Exception as e:
            log.exception("unexpected error in obtain access token", user_id=request.user_id)
            raise ObtainAccessTokenError("unexpected error") from e
