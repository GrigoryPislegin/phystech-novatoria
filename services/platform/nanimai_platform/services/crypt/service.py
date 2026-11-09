import json
from typing import Any, final
from urllib import parse

import structlog
from pydantic import BaseModel

from nanimai_platform.protocols.external.crypt import CryptProtocol
from nanimai_platform.utils.logging_span import span

log = structlog.stdlib.get_logger("app.service.CryptService")


class CryptServiceError(Exception): ...


class CryptServiceInvalidDataError(Exception): ...


@final
class CryptService:
    def __init__(
        self,
        crypt_x25519_adapter: CryptProtocol,
    ):
        self._crypt_x25519_adapter = crypt_x25519_adapter

    class EncryptDictRequest(BaseModel):
        data: dict[str, Any]

    @span(op="crypt_service", name="encrypt_dict")
    def encrypt_dict(self, request: EncryptDictRequest) -> str:
        try:
            plaintext = json.dumps(request.data, ensure_ascii=False, separators=(",", ":"))
            encrypted = self._crypt_x25519_adapter.encrypt(plaintext)
            return parse.quote_plus(encrypted)
        except Exception as e:
            log.error("failed to encrypt dict", err=e)
            raise CryptServiceError("unknown error") from e

    class DecryptDictRequest(BaseModel):
        data: str

    @span(op="crypt_service", name="decrypt_str_to_dict")
    def decrypt_dict(self, request: DecryptDictRequest) -> dict[str, Any]:
        try:
            encrypted = parse.unquote(request.data)
            plain_text = self._crypt_x25519_adapter.decrypt(encrypted)

            data = json.loads(plain_text)
            if not isinstance(data, dict):
                raise CryptServiceInvalidDataError("payload is not a JSON object")

            return data
        except CryptServiceInvalidDataError as e:
            log.error("missing keys in dict", err=e)
            raise e
        except Exception as e:
            log.error("failed to decrypt dict", err=e)
            raise CryptServiceError("unknown error") from e
