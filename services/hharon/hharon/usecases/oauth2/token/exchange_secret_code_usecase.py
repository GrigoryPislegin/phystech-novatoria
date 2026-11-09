from typing import final

import pydantic
import structlog

from hharon.protocols import oauth2 as oauth2_protocol
from hharon.usecases.oauth2.state import EncryptOAuthState, EncryptOAuthStateDecryptError

log = structlog.stdlib.get_logger("hharon.usecases.oauth2.token.ExchangeSecretCode")


class ExchangeSecretCodeError(Exception):
    """Base exception class for ExchangeSecretCode errors."""


class ExchangeSecretCodeDecryptError(ExchangeSecretCodeError):
    """Decryption error raised by ExchangeSecretCode."""


class ExchangeSecretCodeInvalidStateError(ExchangeSecretCodeError):
    """Invalid state error raised by ExchangeSecretCode (business logic error)."""


class ExchangeSecretCodeAPIError(ExchangeSecretCodeError):
    """API error raised by ExchangeSecretCode."""


@final
class ExchangeSecretCode:
    def __init__(
        self,
        *,
        hh_oauth2_adapter: oauth2_protocol.OAuth2Protocol,
        encrypt_state_usecase: EncryptOAuthState,
    ) -> None:
        self._hh_oauth2_adapter = hh_oauth2_adapter
        self._encrypt_state_usecase = encrypt_state_usecase

    class ExchangeSecretCodeRequest(pydantic.BaseModel):
        """Request to exchange secret code for tokens."""

        secret_code: str
        encrypted_state: str
        redirect_uri: str

    class ExchangeSecretCodeResponse(pydantic.BaseModel):
        """Response with OAuth2 tokens."""

        access_token: str
        refresh_token: str
        expires_in: int

    async def exchange_secret_code(self, request: ExchangeSecretCodeRequest) -> ExchangeSecretCodeResponse:
        try:
            if not request.encrypted_state:
                log.warning("Empty encrypted state provided")
                raise ExchangeSecretCodeInvalidStateError("empty state")

            log.debug(
                "Decrypting OAuth state",
                state_length=len(request.encrypted_state) if request.encrypted_state else 0,
            )
            decrypted_state = self._encrypt_state_usecase.decrypt_oauth_state(
                EncryptOAuthState.DecryptOAuthStateRequest(state=request.encrypted_state)
            )
            log.debug("Successfully decrypted state", user_id=decrypted_state.user_id)

            log.debug(
                "Exchanging secret code for tokens",
                code_length=len(request.secret_code) if request.secret_code else 0,
                user_id=decrypted_state.user_id,
            )
            token_response = await self._hh_oauth2_adapter.get_token_by_secret_code(
                oauth2_protocol.OAuth2Protocol.GetTokensBySecretCodeRequest(
                    secret_code=request.secret_code,
                    redirect_uri=request.redirect_uri,
                )
            )

            log.info(
                "Successfully exchanged secret code for tokens",
                user_id=decrypted_state.user_id,
                expires_in=token_response.token.expires_in,
            )

            return self.ExchangeSecretCodeResponse(
                access_token=token_response.token.access_token,
                refresh_token=token_response.token.refresh_token,
                expires_in=token_response.token.expires_in,
            )
        except ExchangeSecretCodeInvalidStateError:
            raise
        except EncryptOAuthStateDecryptError as e:
            log.exception("failed to decrypt oauth state")
            raise ExchangeSecretCodeDecryptError("failed to decrypt state") from e
        except oauth2_protocol.OAuth2ValidateError as e:
            log.exception(
                "failed to exchange code for tokens via API (validation)",
                code_length=len(request.secret_code) if request.secret_code else 0,
            )
            msg = f"failed to validate api response: {e!s}"
            raise ExchangeSecretCodeAPIError(msg) from e
        except oauth2_protocol.OAuth2APIError as e:
            log.exception(
                "failed to exchange code for tokens via API (api)",
                error_details=str(e),
                code_length=len(request.secret_code) if request.secret_code else 0,
            )
            msg = f"failed to send request to api: {e!s}"
            raise ExchangeSecretCodeAPIError(msg) from e
        except oauth2_protocol.OAuth2Error as e:
            log.exception("failed to exchange code for tokens via API")
            raise ExchangeSecretCodeAPIError("unknown error") from e
        except Exception as e:
            log.exception("unexpected error in exchange secret code")
            raise ExchangeSecretCodeError("unexpected error") from e
