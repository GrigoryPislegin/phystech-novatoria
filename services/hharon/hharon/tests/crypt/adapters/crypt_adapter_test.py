import pytest

from hharon import infra, protocols
from hharon.adapters.crypt import adapter as cipher_adapter


def test_crypt_adapter_generate_valid_keypair() -> None:
    kp = cipher_adapter.CryptEciesX25519Adapter.generate_keypair()
    assert isinstance(kp.private_hex, str)
    assert isinstance(kp.public_hex, str)
    assert len(kp.private_hex) == 64
    assert len(kp.public_hex) == 64

    _ = cipher_adapter.CryptEciesX25519Adapter(
        cfg=infra.CryptConfig(private_key_hex=kp.private_hex, public_key_hex=kp.public_hex)
    )


def test_crypt_adapter_validate_keypair():
    # invalid
    with pytest.raises(protocols.CryptProtocolInvalidKeyError):
        _ = cipher_adapter.CryptEciesX25519Adapter(
            cfg=infra.CryptConfig(private_key_hex="invalid", public_key_hex="invalid")
        )

    # invalid
    with pytest.raises(protocols.CryptProtocolInvalidKeyError):
        _ = cipher_adapter.CryptEciesX25519Adapter(
            cfg=infra.CryptConfig(private_key_hex="0" * 64, public_key_hex="0" * 64)
        )

    # valid
    _ = cipher_adapter.CryptEciesX25519Adapter(cfg=infra.CryptConfig(private_key_hex="F" * 64, public_key_hex="F" * 64))


def test_crypt_adapter_encrypt_decrypt_roundtrip() -> None:
    kp = cipher_adapter.CryptEciesX25519Adapter.generate_keypair()
    adapter = cipher_adapter.CryptEciesX25519Adapter(
        cfg=infra.CryptConfig(private_key_hex=kp.private_hex, public_key_hex=kp.public_hex)
    )

    plain = b"hello-ru-\xd0\xbf\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82"
    encrypted = adapter.encrypt(plain)
    assert isinstance(encrypted, bytes)
    assert encrypted != plain
    decrypted = adapter.decrypt(encrypted)
    assert decrypted == plain
