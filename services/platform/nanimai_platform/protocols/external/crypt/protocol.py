from abc import ABC, abstractmethod

from pydantic import BaseModel


class CryptProtocol(ABC):
    class KeyPair(BaseModel):
        private_hex: str
        public_hex: str

    @abstractmethod
    def generate_keypair(self) -> KeyPair:
        """Generates keys pair and transforms to hex.
        Mostly used to print and fill in the Config.
        """
        ...

    @abstractmethod
    def encrypt(self, plain_text: str) -> str:
        """
        Encrypts plain_text.
        Returns base64 encoded string.
        """
        ...

    @abstractmethod
    def decrypt(self, encrypted_text: str) -> str:
        """
        Decrypts encrypted_text.
        Receives base64 encoded string, returns plain_text.
        """
        ...
