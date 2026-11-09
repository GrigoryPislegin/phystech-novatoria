from pydantic import EmailStr
from pydantic.fields import Field

from nanimai_platform.cmd.server.utils.dtobase import DTOBase
from nanimai_platform.domain import Oauth2SourceEnum
from nanimai_platform.domain.scalar.scalars import UserID
from nanimai_platform.domain.user_profile.user_profile import Tutorials


class TariffDTO(DTOBase):
    title: str
    analysis_total: int
    analysis_used: int


class TutorialsDTO(DTOBase):
    platform: bool | None = None
    interview: bool | None = None


class PutUserRequestDTO(DTOBase):
    name: str | None = None
    tutorials: TutorialsDTO | None = None


class UserResponseDTO(DTOBase):
    id: UserID
    name: str
    email: EmailStr
    thumbnail_url: str
    tariff: TariffDTO = Field(deprecated="use /api/v1/balance")
    tutorials: Tutorials


class HeadHunterDTO(DTOBase):
    status: bool
    name: str
    email: str


class ActiveIntegrationsResponseDTO(DTOBase):
    active_integrations: dict[Oauth2SourceEnum, bool] = Field(deprecated="use corresponding fields instead")
    hh: HeadHunterDTO | None = None
