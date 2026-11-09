from __future__ import annotations

from nanimai_platform.adapters.external.crypt.ecies_x25519.adapter import CryptX25519Adapter


def test_crypt_x25519_adapter_encrypt_decrypt_roundtrip() -> None:
    tmp = CryptX25519Adapter(private_hex="0" * 64, public_hex="0" * 64)
    kp = tmp.generate_keypair()
    adapter = CryptX25519Adapter(private_hex=kp.private_hex, public_hex=kp.public_hex)

    plain = "hello-ru-привет"
    encrypted = adapter.encrypt(plain)
    assert isinstance(encrypted, str)
    assert encrypted != plain
    decrypted = adapter.decrypt(encrypted)
    assert decrypted == plain
