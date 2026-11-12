from typing import override

import pytest

from hharon import infra
from hharon.adapters.crypt import adapter as cipher_adapter
from hharon.protocols import crypt as crypt_protocol
from hharon.usecases.crypt import cipher


def test_cipher_encrypt_decrypt_roundtrip() -> None:
    kp = cipher_adapter.CryptEciesX25519Adapter.generate_keypair()
    adapter = cipher_adapter.CryptEciesX25519Adapter(
        cfg=infra.CryptConfig(private_key_hex=kp.private_hex, public_key_hex=kp.public_hex)
    )
    usecase = cipher.CipherUsecase(crypt_adapter=adapter)

    plaintext = b"hello-ru-\xd0\xbf\xd1\x80\xd0\xb8\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82"

    encrypted = usecase.encrypt_bytes(cipher.CipherUsecase.EncryptBytesRequest(data=plaintext))
    assert isinstance(encrypted.data, bytes)
    assert encrypted.data != plaintext

    decrypted = usecase.decrypt_bytes(cipher.CipherUsecase.DecryptBytesRequest(data=encrypted.data))
    assert decrypted.data == plaintext


def test_cipher_encrypt_wraps_unexpected_errors() -> None:
    class _BrokenAdapter(crypt_protocol.CryptProtocol):
        @override
        @classmethod
        def generate_keypair(cls) -> crypt_protocol.CryptProtocol.KeyPair:
            raise NotImplementedError

        @override
        def encrypt(self, plaintext: bytes) -> bytes:
            raise RuntimeError("boom")

        @override
        def decrypt(self, ciphertext: bytes) -> bytes:
            return b"ok"

    usecase = cipher.CipherUsecase(crypt_adapter=_BrokenAdapter())

    with pytest.raises(cipher.CipherUsecaseEncryptError):
        _ = usecase.encrypt_bytes(cipher.CipherUsecase.EncryptBytesRequest(data=b"data"))


def test_cipher_decrypt_wraps_unexpected_errors() -> None:
    invalid_ciphertext = b"not-a-valid-ciphertext"

    class _BrokenAdapter(crypt_protocol.CryptProtocol):
        @override
        @classmethod
        def generate_keypair(cls) -> crypt_protocol.CryptProtocol.KeyPair:
            raise NotImplementedError

        @override
        def encrypt(self, plaintext: bytes) -> bytes:  # pragma: no cover - not used in this scenario
            return b"ok"

        @override
        def decrypt(self, ciphertext: bytes) -> bytes:
            msg = f"cannot decrypt payload: {ciphertext!r}"
            raise ValueError(msg)

    usecase = cipher.CipherUsecase(crypt_adapter=_BrokenAdapter())

    with pytest.raises(cipher.CipherUsecaseDecryptError):
        _ = usecase.decrypt_bytes(cipher.CipherUsecase.DecryptBytesRequest(data=invalid_ciphertext))
