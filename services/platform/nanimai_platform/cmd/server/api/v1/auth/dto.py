from pydantic import EmailStr, Field

from nanimai_platform.cmd.server.utils.dtobase import DTOBase
from nanimai_platform.domain.scalar.scalars import UserID
from nanimai_platform.domain.user_profile.user_profile import Tutorials


class TariffDTO(DTOBase):
    title: str
    analysis_total: int
    analysis_used: int


class SignUpRequestDTO(DTOBase):
    name: str = Field(min_length=2, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8)


class UserDTO(DTOBase):
    id: UserID
    name: str
    email: EmailStr
    thumbnail_url: str
    tariff: TariffDTO = Field(deprecated="use /api/v1/balance")
    tutorials: Tutorials


class SignUpResponseDTO(DTOBase):
    user: UserDTO
    access_token: str
    refresh_token: str


class SignInRequestDTO(DTOBase):
    email: EmailStr
    password: str = Field(min_length=8)


class SignInResponseDTO(DTOBase):
    user: UserDTO
    access_token: str
    refresh_token: str


class RefreshTokenResponseDTO(DTOBase):
    access_token: str
    refresh_token: str
