from abc import ABC, abstractmethod

from pydantic import BaseModel


class CryptProtocolInvalidKeyError(Exception):
    """Exception raised when an invalid key is used."""


class CryptProtocol(ABC):
    """Protocol for asymmetric encryption of arbitrary bytes."""

    class KeyPair(BaseModel):
        private_hex: str
        public_hex: str

    @classmethod
    @abstractmethod
    def generate_keypair(cls) -> KeyPair:
        """Generate a new key pair and return it in hex representation."""
        ...

    @abstractmethod
    def encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt raw bytes and return encrypted bytes."""
        ...

    @abstractmethod
    def decrypt(self, ciphertext: bytes) -> bytes:
        """Decrypt raw bytes and return original bytes."""
        ...
