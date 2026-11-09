from hharon import infra
from hharon.adapters.crypt import adapter as cipher_adapter
from hharon.usecases.crypt import cipher as cipher_usecase


def test_cipher_usecase_encrypt_decrypt_roundtrip() -> None:
    kp = cipher_adapter.CryptEciesX25519Adapter.generate_keypair()
    cfg = infra.CryptConfig(private_key_hex=kp.private_hex, public_key_hex=kp.public_hex)
    adapter = cipher_adapter.CryptEciesX25519Adapter(cfg=cfg)

    usecase = cipher_usecase.CipherUsecase(crypt_adapter=adapter)
    plaintext = b"hello-ru-\xd0\xbf\xd1\x80\xd0\xb8\xd0\xb5\xd1\x82"

    encrypted = usecase.encrypt_bytes(cipher_usecase.CipherUsecase.EncryptBytesRequest(data=plaintext))
    assert isinstance(encrypted.data, bytes)
    assert encrypted.data != plaintext

    decrypted = usecase.decrypt_bytes(cipher_usecase.CipherUsecase.DecryptBytesRequest(data=encrypted.data))
    assert decrypted.data == plaintext
