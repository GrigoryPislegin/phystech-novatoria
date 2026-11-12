from typing import final, override

import ecies

from hharon.infra.crypt import CryptConfig
from hharon.protocols import crypt as crypt_protocol


@final
class CryptEciesX25519Adapter(crypt_protocol.CryptProtocol):
    """eciespy-based adapter (x25519 curve) for the byte-level CryptProtocol."""

    ECIES_CONFIG = ecies.config.Config(elliptic_curve="x25519")

    def __init__(self, *, cfg: CryptConfig) -> None:
        # validate keys on initialization
        try:
            self._secret_key = ecies.keys.PrivateKey.from_hex(
                curve=self.ECIES_CONFIG.elliptic_curve, sk_hex=cfg.private_key_hex
            )
            self._public_key = ecies.keys.PublicKey.from_hex(
                curve=self.ECIES_CONFIG.elliptic_curve, pk_hex=cfg.public_key_hex
            )
        except ValueError as e:
            raise crypt_protocol.CryptProtocolInvalidKeyError from e

    @override
    @classmethod
    def generate_keypair(cls) -> crypt_protocol.CryptProtocol.KeyPair:
        """Generate a new keypair using the configured elliptic curve."""
        sk = ecies.keys.PrivateKey(cls.ECIES_CONFIG.elliptic_curve)
        return crypt_protocol.CryptProtocol.KeyPair(
            private_hex=sk.to_hex(),
            public_hex=sk.public_key.to_hex(),
        )

    @override
    def encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt bytes using the configured curve."""
        return ecies.encrypt(self._public_key.to_hex(), plaintext, config=self.ECIES_CONFIG)

    @override
    def decrypt(self, ciphertext: bytes) -> bytes:
        """Decrypt bytes using the configured curve."""
        return ecies.decrypt(self._secret_key.to_hex(), ciphertext, config=self.ECIES_CONFIG)
