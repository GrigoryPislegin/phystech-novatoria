from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field
from pydantic_extra_types.currency_code import ISO4217 as CurrencyISO4217

from nanimai_platform.domain.scalar.scalars import ProjectID, UserID, VacancyID
from nanimai_platform.domain.skill import Skill
from nanimai_platform.utils import TimeBaseModel


class VacancyStatus(StrEnum):
    OPEN = "open"
    ARCHIVED = "archived"


class ScheduleEnum(StrEnum):
    SCHEDULE_6_1 = "6/1"
    SCHEDULE_5_2 = "5/2"
    SCHEDULE_4_3 = "4/3"
    SCHEDULE_3_3 = "3/3"
    SCHEDULE_3_2 = "3/2"
    SCHEDULE_2_2 = "2/2"
    SCHEDULE_2_1 = "2/1"
    SCHEDULE_1_1 = "1/1"


class ExperienceEnum(StrEnum):
    EXP_0 = "no"
    EXP_1_3 = "1-3"
    EXP_3_6 = "3-6"
    EXP_6_PLUS = "6+"


class WorkFormatEnum(StrEnum):
    OFFICE = "office"
    REMOTE = "remote"
    HYBRID = "hybrid"
    TRAVEL = "travel"


class WorkTypeEnum(StrEnum):
    FULL_TIME = "full-time"
    PART_TIME = "part-time"
    PROJECT = "project"
    SHIFT = "shift"


class VacancyStageEnum(StrEnum):
    MAGIC_AI = "magic-ai"
    """ Оценка ИИ """

    SELECTED_AI = "new"
    """ Отобрано ИИ """

    SELECTED_USER = "selected"
    """ Отобранно вами """

    MESSAGE = "message"
    """ Сообщение кандидату """

    PRELIMINARY_CALL = "preliminary_call"
    """ Предварительный звонок """

    INTERVIEW = "interview"
    """ Собеседование """

    TEST_TASK = "test_task"
    """ Тестовое задание """

    FINAL_TEST = "final_test"
    """ Финалисты """

    ACCEPTED = "accepted"
    """ Оффер """

    REJECTED_AI = "rejected"
    """ Отклоненные ИИ """

    REJECTED_USER = "rejected_user"
    """ Отклоненные вами """

    OFFER = "offer"
    """ Оффер """


class VacancyStageStatus(BaseModel):
    stage: VacancyStageEnum
    shown: bool = True


class PublicationStatusEnum(StrEnum):
    NOT_PUBLISHED = "not_published"
    SUBMITTED = "submitted"
    PROCESSED = "processed"
    PUBLISHED = "published"


class SalaryAmountRange(BaseModel):
    currency: Annotated[CurrencyISO4217, str] = Field(
        default=CurrencyISO4217("RUB"),
        description="currency in ISO 4217 format",
    )
    min: int | None = Field(description="minimum salary")
    max: int | None = Field(description="maximum salary")


class PublicationStatus(BaseModel):
    state: PublicationStatusEnum = Field(description="publication status")
    url: str | None = Field(description="publication url")
    publication_id: str | None = Field(description="publication id")


class VacancyPublication(BaseModel):
    hh: PublicationStatus
    avito: PublicationStatus


class VacancyPublicationSourceEnum(StrEnum):
    HH = "hh"
    AVITO = "avito"


class VacancyStatistics(BaseModel):
    total_candidates: int = Field(description="total number of candidates")
    platform_candidates: int = Field(description="number of platform candidates")
    delegated_candidates: int = Field(description="number of delegated candidates")


class Vacancy(TimeBaseModel):
    id: VacancyID = Field(description="vacancy id")
    user_id: UserID = Field(description="vacancy owner")
    project_id: ProjectID = Field(description="project id")
    title: str = Field(description="vacancy title")
    description: str = Field(description="vacancy description")
    specialization: str = Field(description="vacancy specialization")
    thumbnail_url: str = Field(description="vacancy thumbnail url")
    status: VacancyStatus = Field(description="vacancy status")
    city: str | None = Field(description="vacancy city")
    country: str | None = Field(description="vacancy country")
    hire_amount: int | None = Field(description="vacancy hire amount")
    salary: SalaryAmountRange | None = Field(description="vacancy salary")
    work_type: WorkTypeEnum = Field(description="vacancy work type")
    work_format: list[WorkFormatEnum] = Field(description="vacancy work format")
    is_internship: bool = Field(description="vacancy is internship")
    is_temphire: bool = Field(description="vacancy is temporary hire")
    schedule: list[ScheduleEnum] = Field(description="vacancy schedule")
    daily_rate: list[int] = Field(description="how many hours per day, multi-choice")
    experience: ExperienceEnum = Field(description="vacancy experience")
    skills: list[Skill] = Field(description="list of skills")
    stages: list[VacancyStageStatus] = Field(description="list of stages")
    publication: VacancyPublication = Field(description="vacancy publication")
    statistics: VacancyStatistics = Field(description="vacancy statistics")
    threshold: float = Field(ge=0, le=1, description="vacancy threshold for approving candidates")
