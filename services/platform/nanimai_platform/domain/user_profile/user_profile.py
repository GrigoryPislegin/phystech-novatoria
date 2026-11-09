from pydantic import BaseModel, EmailStr, Field

from nanimai_platform.domain.scalar import UserID
from nanimai_platform.utils import TimeBaseModel


class Tariff(BaseModel):
    title: str
    analysis_total: int
    analysis_used: int


class Tutorials(BaseModel):
    platform: bool
    interview: bool


class UserProfile(TimeBaseModel):
    id: UserID = Field(description="user id")
    email: EmailStr = Field(description="user email")
    name: str = Field(description="name")
    password: str = Field(description="password hash")
    thumbnail_url: str = Field(description="thumbnail url")
    tariff: Tariff = Field(description="tariff")
    tutorials: Tutorials = Field(description="tutorials")
