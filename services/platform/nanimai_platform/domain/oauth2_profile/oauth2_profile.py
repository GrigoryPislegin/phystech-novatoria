from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from nanimai_platform.domain.scalar import OAuth2ProfileID, UserID
from nanimai_platform.utils import TimeBaseModel


class Oauth2SourceEnum(StrEnum):
    HH = "hh"


class Token(BaseModel):
    access_token: str
    expires_in: int
    expires_at: datetime
    token_type: str
    refresh_token: str


class OAuth2Profile(TimeBaseModel):
    id: OAuth2ProfileID = Field(description="oauth2 id")
    user_id: UserID = Field(description="user id")
    source: Oauth2SourceEnum = Field(description="oauth2 source")
    token: Token | None = Field(description="encrypted oauth2 access and refresh token")
