from nanimai_platform.cmd.server.utils.dtobase import DTOBase


class InitOAuth2FlowRequestDTO(DTOBase):
    redirect_back: str


class CompleteOAuth2FlowRequestDTO(DTOBase):
    code: str | None = None
    error: str | None = None
    state: str


class Oauth2LinkDTO(DTOBase):
    redirect_url: str
