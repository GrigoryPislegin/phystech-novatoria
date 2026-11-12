from datetime import datetime
from typing import Annotated

from fastapi import UploadFile
from pydantic import Field
from pydantic_extra_types.currency_code import ISO4217

from nanimai_platform.cmd.server.api.common import common_dto
from nanimai_platform.cmd.server.utils.dtobase import DTOBase
from nanimai_platform.domain import (
    CriterionPayload,
    ExperienceEnum,
    ProjectID,
    PublicationStatusEnum,
    ScheduleEnum,
    UserID,
    Vacancy,
    VacancyStatus,
    WorkFormatEnum,
    WorkTypeEnum,
)


class ParseVacancyFormRequestDTO(DTOBase):
    project_id: ProjectID
    file: UploadFile


class ParseVacancyStageDTO(DTOBase):
    kind: common_dto.VacancyColumnEnum
    shown: bool = True


class ParseVacancySalaryAmountRangeDTO(DTOBase):
    currency: Annotated[ISO4217, str]
    min: int | None
    max: int | None


class PublicationStatusDTO(DTOBase):
    state: PublicationStatusEnum
    url: str | None


class PublicationDTO(DTOBase):
    hh: PublicationStatusDTO
    avito: PublicationStatusDTO


class ParseVacancyResponseDTO(DTOBase):
    user_id: UserID
    project_id: ProjectID
    status: VacancyStatus

    created_at: datetime
    updated_at: datetime

    title: str
    description: str
    specialization: str
    hire_amount: int | None
    thumbnail_url: str
    salary: ParseVacancySalaryAmountRangeDTO | None

    city: str | None
    country: str | None
    schedule: list[ScheduleEnum]
    work_type: WorkTypeEnum
    is_internship: bool
    is_temphire: bool
    daily_rate: list[int]
    experience: ExperienceEnum
    work_format: list[WorkFormatEnum]

    publication: PublicationDTO

    skills: list[str]

    stages: list[ParseVacancyStageDTO]
    threshold: float

    @staticmethod
    def from_domain(vacancy: Vacancy) -> "ParseVacancyResponseDTO":
        return ParseVacancyResponseDTO(
            user_id=vacancy.user_id,
            project_id=vacancy.project_id,
            status=vacancy.status,
            created_at=vacancy.created_at,
            updated_at=vacancy.updated_at,
            title=vacancy.title,
            description=vacancy.description,
            specialization=vacancy.specialization,
            hire_amount=vacancy.hire_amount,
            thumbnail_url=vacancy.thumbnail_url,
            city=vacancy.city,
            country=vacancy.country,
            schedule=vacancy.schedule,
            work_type=vacancy.work_type,
            experience=vacancy.experience,
            salary=ParseVacancySalaryAmountRangeDTO(
                currency=vacancy.salary.currency,
                min=vacancy.salary.min,
                max=vacancy.salary.max,
            )
            if vacancy.salary is not None
            else None,
            skills=[s.title for s in vacancy.skills],
            is_internship=vacancy.is_internship,
            is_temphire=vacancy.is_temphire,
            daily_rate=vacancy.daily_rate,
            work_format=vacancy.work_format,
            stages=[ParseVacancyStageDTO(kind=stage.stage, shown=stage.shown) for stage in vacancy.stages],
            publication=PublicationDTO(
                hh=PublicationStatusDTO(
                    state=vacancy.publication.hh.state,
                    url=vacancy.publication.hh.url,
                ),
                avito=PublicationStatusDTO(
                    state=vacancy.publication.avito.state,
                    url=vacancy.publication.avito.url,
                ),
            ),
            threshold=vacancy.threshold,
        )


class PublishToDTO(DTOBase):
    hh: bool = False
    # add more platforms when needed


class ParseVacancyRequestDTO(DTOBase):
    project_id: ProjectID
    title: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1, max_length=15000)
    specialization: str = Field(min_length=1, max_length=500)
    status: VacancyStatus | None = None
    city: str | None = Field(max_length=100, default=None)
    country: str | None = Field(max_length=100, default=None)
    hire_amount: int | None = None
    salary: ParseVacancySalaryAmountRangeDTO | None = None
    work_type: WorkTypeEnum | None = None
    work_format: list[WorkFormatEnum] | None = None
    is_internship: bool | None = None
    is_temphire: bool | None = None
    schedule: list[ScheduleEnum] | None = None
    daily_rate: list[int] | None = None
    experience: ExperienceEnum | None = None
    skills: list[str]
    stages: list[ParseVacancyStageDTO] | None = None
    publish_to: PublishToDTO | None = None


class CriterionPayloadResponseDTO(DTOBase):
    criterion: str
    initial_weight: int = Field(ge=0)

    @staticmethod
    def from_domain(criterion_payload: CriterionPayload) -> "CriterionPayloadResponseDTO":
        return CriterionPayloadResponseDTO(
            criterion=criterion_payload.criterion,
            initial_weight=criterion_payload.initial_weight,
        )


class GetManyCriterionPayloadsResponseDTO(DTOBase):
    criterion_payloads: list[CriterionPayloadResponseDTO]
