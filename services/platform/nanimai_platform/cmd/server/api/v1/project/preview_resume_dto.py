from nanimai_platform.cmd.server.utils.dtobase import DTOBase


class PostPreviewResumeRequestDTO(DTOBase):
    logo: str | None = None
    logo_format: str | None = None
    main_color: str | None = None
    without_nanimai_attributes: bool = False


class PostPreviewResumeResponseDTO(DTOBase):
    download_link: str
