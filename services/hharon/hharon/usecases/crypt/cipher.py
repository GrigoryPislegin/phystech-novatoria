from typing import final

import pydantic
import structlog

from hharon.protocols import crypt as crypt_protocol

log = structlog.stdlib.get_logger("hharon.usecases.CipherUsecase")


class CipherUsecaseError(Exception):
    """Base exception class for CipherUsecase errors."""


class CipherUsecaseEncryptError(CipherUsecaseError):
    """Encryption error raised by CipherUsecase."""


class CipherUsecaseDecryptError(CipherUsecaseError):
    """Decryption error raised by CipherUsecase."""


@final
class CipherUsecase:
    """Usecase for encrypting and decrypting arbitrary byte payloads."""

    def __init__(self, *, crypt_adapter: crypt_protocol.CryptProtocol) -> None:
        self._crypt_adapter = crypt_adapter

    class EncryptBytesRequest(pydantic.BaseModel):
        data: bytes

    class EncryptBytesResponse(pydantic.BaseModel):
        data: bytes

    class DecryptBytesRequest(pydantic.BaseModel):
        data: bytes

    class DecryptBytesResponse(pydantic.BaseModel):
        data: bytes

    def encrypt_bytes(self, request: EncryptBytesRequest) -> EncryptBytesResponse:
        try:
            encrypted = self._crypt_adapter.encrypt(request.data)
        except Exception as exc:
            log.exception("failed to encrypt bytes")
            raise CipherUsecaseEncryptError("failed to encrypt data") from exc
        return self.EncryptBytesResponse(data=encrypted)

    def decrypt_bytes(self, request: DecryptBytesRequest) -> DecryptBytesResponse:
        try:
            decrypted = self._crypt_adapter.decrypt(request.data)
        except Exception as exc:
            log.exception("failed to decrypt bytes")
            raise CipherUsecaseDecryptError("failed to decrypt data") from exc
        return self.DecryptBytesResponse(data=decrypted)
