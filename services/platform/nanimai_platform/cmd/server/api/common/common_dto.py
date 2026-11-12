from typing import Annotated

from nanimai_platform.domain import VacancyStageEnum
from nanimai_platform.utils.pydantic_enum_by_name_or_value import ByNameOrValue

type VacancyColumnEnum = Annotated[VacancyStageEnum, ByNameOrValue(VacancyStageEnum)]
