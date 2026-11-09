from nanimai_platform.cmd.server.utils.dtobase import DTOBase


class SkillRecommendationRequestDTO(DTOBase):
    job_sphere: str
    job_name: str


class SkillRecommendationResponseDTO(DTOBase):
    skills: list[str]
