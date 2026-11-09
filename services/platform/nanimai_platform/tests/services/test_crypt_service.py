from __future__ import annotations

import pytest

from nanimai_platform.services.crypt import service as crypt_service


class _DummyCryptAdapter:
    def encrypt(self, plain_text: str) -> str:
        return f"enc:{plain_text}"

    def decrypt(self, encrypted_text: str) -> str:
        prefix = "enc:"
        if not encrypted_text.startswith(prefix):
            raise ValueError("bad cipher")
        return encrypted_text.removeprefix(prefix)


def test_crypt_service_encrypt_decrypt_dict_roundtrip_urlsafe() -> None:
    svc = crypt_service.CryptService(crypt_x25519_adapter=_DummyCryptAdapter())  # type: ignore[arg-type]
    payload = {"user_id": "u1", "redirect_back": "https://example.com/callback?x=1&y=2", "ru": "привет"}

    encrypted = svc.encrypt_dict(crypt_service.CryptService.EncryptDictRequest(data=payload))
    # state должен быть url-safe строкой (т.к. кладём в query param)
    assert isinstance(encrypted, str)
    assert encrypted != ""
    assert "%" in encrypted or "+" in encrypted

    decrypted = svc.decrypt_dict(crypt_service.CryptService.DecryptDictRequest(data=encrypted))
    assert decrypted == payload


def test_crypt_service_decrypt_dict_rejects_non_object_json() -> None:
    class _Adapter:
        def encrypt(self, plain_text: str) -> str:
            return "enc:any"

        def decrypt(self, encrypted_text: str) -> str:
            return "[]"

    svc = crypt_service.CryptService(crypt_x25519_adapter=_Adapter())  # type: ignore[arg-type]
    with pytest.raises(crypt_service.CryptServiceInvalidDataError):
        _ = svc.decrypt_dict(crypt_service.CryptService.DecryptDictRequest(data="anything"))


def test_crypt_service_encrypt_wraps_unexpected_errors() -> None:
    class _Adapter:
        def encrypt(self, plain_text: str) -> str:
            raise RuntimeError("boom")

        def decrypt(self, encrypted_text: str) -> str:
            return "ok"

    svc = crypt_service.CryptService(crypt_x25519_adapter=_Adapter())  # type: ignore[arg-type]
    with pytest.raises(crypt_service.CryptServiceError):
        _ = svc.encrypt_dict(crypt_service.CryptService.EncryptDictRequest(data={"k": "v"}))
