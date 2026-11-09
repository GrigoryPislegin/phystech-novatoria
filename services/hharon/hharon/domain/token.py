from datetime import datetime
from typing import ClassVar

import pydantic


class TokenPair(pydantic.BaseModel):
    """Domain model for HeadHunter OAuth2 token pair."""

    model_config: ClassVar[pydantic.ConfigDict] = pydantic.ConfigDict(frozen=True)

    user_id: str
    encrypted_access_token: bytes
    encrypted_refresh_token: bytes
    expires_at: datetime
    token_type: str
    is_invalid: bool = False
