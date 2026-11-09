from typing import final

import pydantic
import structlog

from hharon.protocols import token as token_protocol
from hharon.usecases.crypt import CipherUsecase, CipherUsecaseDecryptError

log = structlog.stdlib.get_logger("hharon.usecases.token.GetTokens")


class GetTokensError(Exception):
    """Base exception class for GetTokens errors."""


class GetTokensNotFoundError(GetTokensError):
    """Tokens not found error."""


class GetTokensDecryptError(GetTokensError):
    """Decryption error raised by GetTokens."""


@final
class GetTokens[SessionT]:
    def __init__(
        self,
        *,
        token_repository: token_protocol.HeadHunterTokenRepositoryProtocol[SessionT],
        cipher_usecase: CipherUsecase,
    ) -> None:
        self._token_repository = token_repository
        self._cipher_usecase = cipher_usecase

    class GetTokensRequest(pydantic.BaseModel):
        """Request to get tokens."""

        user_id: str

    class GetTokensResponse(pydantic.BaseModel):
        """Response with decrypted tokens."""

        access_token: str
        refresh_token: str
        expires_at: pydantic.AwareDatetime
        token_type: str
        is_invalid: bool

    async def get_tokens(self, request: GetTokensRequest) -> GetTokensResponse:
        """Get and decrypt tokens from the repository."""
        try:
            log.debug("Getting tokens from repository", user_id=request.user_id)

            async with self._token_repository.context() as session:
                token_pair = await self._token_repository.get_tokens(
                    session,
                    token_protocol.HeadHunterTokenRepositoryProtocol.GetTokensRequest(user_id=request.user_id),
                )

            if token_pair is None:
                log.warning("Tokens not found", user_id=request.user_id)
                error_msg = f"Tokens not found for user_id: {request.user_id}"
                raise GetTokensNotFoundError(error_msg)

            if token_pair.is_invalid:
                log.warning("Tokens are marked as invalid", user_id=request.user_id)
                error_msg = f"Tokens are invalid for user_id: {request.user_id}"
                raise GetTokensNotFoundError(error_msg)

            log.debug("Decrypting tokens", user_id=request.user_id)

            # Decrypt access token
            decrypt_access_response = self._cipher_usecase.decrypt_bytes(
                CipherUsecase.DecryptBytesRequest(data=token_pair.encrypted_access_token)
            )
            access_token = decrypt_access_response.data.decode("utf-8")

            # Decrypt refresh token
            decrypt_refresh_response = self._cipher_usecase.decrypt_bytes(
                CipherUsecase.DecryptBytesRequest(data=token_pair.encrypted_refresh_token)
            )
            refresh_token = decrypt_refresh_response.data.decode("utf-8")

            log.info("Successfully retrieved and decrypted tokens", user_id=request.user_id)

            return self.GetTokensResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=token_pair.expires_at,
                token_type=token_pair.token_type,
                is_invalid=token_pair.is_invalid,
            )
        except GetTokensNotFoundError:
            raise
        except CipherUsecaseDecryptError as e:
            log.exception("failed to decrypt tokens", user_id=request.user_id)
            raise GetTokensDecryptError("failed to decrypt tokens") from e
        except Exception as e:
            log.exception("unexpected error in get tokens", user_id=request.user_id)
            raise GetTokensError("unexpected error") from e
