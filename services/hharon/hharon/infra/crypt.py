from pydantic import BaseModel


class CryptConfig(BaseModel):
    private_key_hex: str
    public_key_hex: str
