from datetime import UTC, datetime, timedelta
from typing import final

import pydantic
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.domain.token import TokenPair
from hharon.protocols import token as token_protocol
from hharon.usecases.crypt import CipherUsecase, CipherUsecaseEncryptError

log = structlog.stdlib.get_logger("hharon.usecases.token.SaveTokens")


class SaveTokensError(Exception):
    """Base exception class for SaveTokens errors."""


class SaveTokensEncryptError(SaveTokensError):
    """Encryption error raised by SaveTokens."""


class SaveTokensRepositoryError(SaveTokensError):
    """Repository error raised by SaveTokens."""


@final
class SaveTokens:
    def __init__(
        self,
        *,
        token_repository: token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession],
        cipher_usecase: CipherUsecase,
    ) -> None:
        self._token_repository = token_repository
        self._cipher_usecase = cipher_usecase

    class SaveTokensRequest(pydantic.BaseModel):
        """Request to save tokens."""

        user_id: str
        access_token: str
        refresh_token: str
        expires_in: int
        token_type: str = "bearer"  # noqa: S105

    class SaveTokensResponse(pydantic.BaseModel):
        """Response with saved token pair."""

        token_pair: TokenPair

    async def save_tokens(self, request: SaveTokensRequest) -> SaveTokensResponse:
        """Save encrypted tokens to the repository."""
        try:
            log.debug("Encrypting tokens", user_id=request.user_id)

            # Encrypt access token
            encrypt_access_response = self._cipher_usecase.encrypt_bytes(
                CipherUsecase.EncryptBytesRequest(data=request.access_token.encode("utf-8"))
            )
            encrypted_access_token = encrypt_access_response.data

            # Encrypt refresh token
            encrypt_refresh_response = self._cipher_usecase.encrypt_bytes(
                CipherUsecase.EncryptBytesRequest(data=request.refresh_token.encode("utf-8"))
            )
            encrypted_refresh_token = encrypt_refresh_response.data

            # Calculate expires_at
            expires_at = datetime.now(UTC) + timedelta(seconds=request.expires_in)

            log.debug("Saving tokens to repository", user_id=request.user_id, expires_at=expires_at)

            async with self._token_repository.context() as session:
                token_pair = await self._token_repository.save_tokens(
                    session,
                    token_protocol.HeadHunterTokenRepositoryProtocol.SaveTokensRequest(
                        user_id=request.user_id,
                        encrypted_access_token=encrypted_access_token,
                        encrypted_refresh_token=encrypted_refresh_token,
                        expires_at=expires_at,
                        token_type=request.token_type,
                    ),
                )

            log.info("Successfully saved tokens", user_id=request.user_id, expires_at=expires_at)

            return self.SaveTokensResponse(token_pair=token_pair)
        except CipherUsecaseEncryptError as e:
            log.exception("failed to encrypt tokens", user_id=request.user_id)
            raise SaveTokensEncryptError("failed to encrypt tokens") from e
        except token_protocol.HeadHunterTokenRepositoryError as e:
            log.exception("failed to save tokens to repository", user_id=request.user_id)
            raise SaveTokensRepositoryError("failed to save tokens") from e
        except Exception as e:
            log.exception("unexpected error in save tokens", user_id=request.user_id)
            raise SaveTokensError("unexpected error") from e
