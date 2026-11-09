import pytest

from hharon import infra
from hharon.adapters.crypt import adapter as cipher_adapter
from hharon.usecases.crypt import cipher
from hharon.usecases.oauth2 import EncryptOAuthState, EncryptOAuthStateDecryptError


def test_encrypt_oauth_state_roundtrip() -> None:
    # Setup cipher adapter

    kp = cipher_adapter.CryptEciesX25519Adapter.generate_keypair()
    adapter = cipher_adapter.CryptEciesX25519Adapter(
        cfg=infra.CryptConfig(private_key_hex=kp.private_hex, public_key_hex=kp.public_hex)
    )

    # Setup usecases
    cipher_usecase = cipher.CipherUsecase(crypt_adapter=adapter)
    encrypt_state_usecase = EncryptOAuthState(cipher_usecase=cipher_usecase)

    user_id = "507f1f77bcf86cd799439011"

    state = encrypt_state_usecase.encrypt_oauth_state(EncryptOAuthState.EncryptOAuthStateRequest(user_id=user_id))
    parsed = encrypt_state_usecase.decrypt_oauth_state(EncryptOAuthState.DecryptOAuthStateRequest(state=state.state))
    assert parsed.user_id == user_id


def test_encrypt_oauth_state_empty_state_raises() -> None:
    # Setup cipher adapter
    kp = cipher_adapter.CryptEciesX25519Adapter.generate_keypair()
    adapter = cipher_adapter.CryptEciesX25519Adapter(
        cfg=infra.CryptConfig(private_key_hex=kp.private_hex, public_key_hex=kp.public_hex)
    )

    # Setup usecases
    cipher_usecase = cipher.CipherUsecase(crypt_adapter=adapter)
    encrypt_state_usecase = EncryptOAuthState(cipher_usecase=cipher_usecase)

    with pytest.raises(EncryptOAuthStateDecryptError):
        _ = encrypt_state_usecase.decrypt_oauth_state(EncryptOAuthState.DecryptOAuthStateRequest(state=""))
