import base64
from typing import override

from ecies import decrypt, encrypt
from ecies.config import ECIES_CONFIG
from ecies.keys import PrivateKey

from nanimai_platform.protocols.external.crypt import CryptProtocol

ECIES_CONFIG.elliptic_curve = "x25519"


class CryptX25519Adapter(CryptProtocol):
    def __init__(self, private_hex: str, public_hex: str):
        self.private_hex = private_hex
        self.public_hex = public_hex

    @override
    def generate_keypair(self) -> CryptProtocol.KeyPair:
        """By Curve25519 (X25519)"""
        sk = PrivateKey("x25519")
        return CryptProtocol.KeyPair(
            private_hex=sk.to_hex(),
            public_hex=sk.public_key.to_hex(),
        )

    @override
    def encrypt(self, plain_text: str) -> str:
        """By Curve25519 (X25519)"""
        encrypted_text_bytes = encrypt(self.public_hex, plain_text.encode())
        return base64.b64encode(encrypted_text_bytes).decode("ascii")

    @override
    def decrypt(self, encrypted_text: str) -> str:
        """By Curve25519 (X25519)"""
        encrypted_text_bytes = base64.b64decode(encrypted_text)
        return decrypt(self.private_hex, encrypted_text_bytes).decode()
