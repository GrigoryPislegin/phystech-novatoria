import base64
from typing import final
from urllib import parse

import pydantic
import structlog

from hharon.usecases.crypt import cipher as cipher_usecase

log = structlog.stdlib.get_logger("hharon.usecases.oauth2.state.EncryptOAuthState")


class EncryptOAuthStateError(Exception):
    """Base exception class for EncryptOAuthState errors."""


class EncryptOAuthStateEncryptError(EncryptOAuthStateError):
    """Encryption error raised by EncryptOAuthState."""


class EncryptOAuthStateDecryptError(EncryptOAuthStateError):
    """Decryption error raised by EncryptOAuthState."""


@final
class EncryptOAuthState:
    def __init__(self, *, cipher_usecase: cipher_usecase.CipherUsecase) -> None:
        self._cipher_usecase = cipher_usecase

    class State(pydantic.BaseModel):
        """Internal state model for OAuth state serialization."""

        user_id: str

    class EncryptOAuthStateRequest(pydantic.BaseModel):
        user_id: str

    class EncryptOAuthStateResponse(pydantic.BaseModel):
        state: str

    class DecryptOAuthStateRequest(pydantic.BaseModel):
        state: str

    class DecryptOAuthStateResponse(pydantic.BaseModel):
        user_id: str

    def encrypt_oauth_state(self, request: EncryptOAuthStateRequest) -> EncryptOAuthStateResponse:
        try:
            state_model = self.State(
                user_id=request.user_id,
            )
            plaintext = state_model.model_dump_json(ensure_ascii=False).encode()

            encrypted_response = self._cipher_usecase.encrypt_bytes(
                cipher_usecase.CipherUsecase.EncryptBytesRequest(data=plaintext)
            )

            encrypted_b64 = base64.urlsafe_b64encode(encrypted_response.data).decode("utf-8")
            state = parse.quote_plus(encrypted_b64)

            return self.EncryptOAuthStateResponse(state=state)
        except cipher_usecase.CipherUsecaseEncryptError as e:
            log.exception("failed to encrypt oauth state")
            raise EncryptOAuthStateEncryptError("failed to encrypt state") from e
        except Exception as e:
            log.exception("unexpected error while encrypting oauth state")
            raise EncryptOAuthStateEncryptError("unexpected error") from e

    def decrypt_oauth_state(self, request: DecryptOAuthStateRequest) -> DecryptOAuthStateResponse:
        try:
            encrypted_b64_str = parse.unquote(request.state)
            encrypted_data = base64.urlsafe_b64decode(encrypted_b64_str)

            decrypted_response = self._cipher_usecase.decrypt_bytes(
                cipher_usecase.CipherUsecase.DecryptBytesRequest(data=encrypted_data)
            )

            plaintext = decrypted_response.data.decode("utf-8")

            try:
                state = self.DecryptOAuthStateResponse.model_validate_json(plaintext)
            except pydantic.ValidationError as e:
                log.exception("failed to validate decrypted state")
                raise EncryptOAuthStateDecryptError("invalid state format") from e
            else:
                return state
        except EncryptOAuthStateError:
            raise
        except cipher_usecase.CipherUsecaseDecryptError as e:
            log.exception("failed to decrypt oauth state")
            raise EncryptOAuthStateDecryptError("failed to decrypt state") from e
        except (UnicodeDecodeError, ValueError) as e:
            log.exception("failed to parse decrypted state")
            raise EncryptOAuthStateDecryptError("invalid state format") from e
        except Exception as e:
            log.exception("unexpected error while decrypting oauth state")
            raise EncryptOAuthStateDecryptError("unexpected error") from e
