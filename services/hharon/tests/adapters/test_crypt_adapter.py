import pytest

from hharon import infra, protocols
from hharon.adapters.crypt import adapter as cipher_adapter


def test_crypt_adapter_validate_key_on_init():
    invalid = infra.CryptConfig(private_key_hex="0" * 64, public_key_hex="0" * 64)
    with pytest.raises(protocols.CryptProtocolInvalidKeyError):
        _ = cipher_adapter.CryptEciesX25519Adapter(cfg=invalid)


def test_crypt_adapter_encrypt_decrypt_roundtrip() -> None:
    kp = cipher_adapter.CryptEciesX25519Adapter.generate_keypair()
    cfg = infra.CryptConfig(private_key_hex=kp.private_hex, public_key_hex=kp.public_hex)
    adapter = cipher_adapter.CryptEciesX25519Adapter(cfg=cfg)

    plain = b"hello-ru-\xd0\xbf\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82"
    encrypted = adapter.encrypt(plain)
    assert isinstance(encrypted, bytes)
    assert encrypted != plain
    decrypted = adapter.decrypt(encrypted)
    assert decrypted == plain
