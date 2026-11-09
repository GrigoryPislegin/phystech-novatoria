from datetime import date, datetime
from typing import Annotated

from pydantic import Field, HttpUrl
from pydantic_extra_types.currency_code import ISO4217
from typing_extensions import deprecated

from nanimai_platform.cmd.server.api.common import common_dto
from nanimai_platform.cmd.server.utils.dtobase import DTOBase
from nanimai_platform.domain import (
    CriterionID,
    ExperienceEnum,
    ProjectID,
    PublicationStatusEnum,
    SalaryAmountRange,
    ScheduleEnum,
    Skill,
    StopFactorID,
    UserID,
    Vacancy,
    VacancyID,
    VacancyStageStatus,
    VacancyStatus,
    WorkFormatEnum,
    WorkTypeEnum,
)
from nanimai_platform.protocols.external.vacancy_importer import VacancyImporterProtocol
from nanimai_platform.services.vacancy import VacancyRichUpdateHook
from nanimai_platform.utils import UpdateValue


class TariffDTO(DTOBase):
    title: str
    analysis_total: int
    analysis_used: int


class SalaryAmountRangeDTO(DTOBase):
    currency: Annotated[ISO4217, str]
    min: int | None
    max: int | None


class StatisticsContainerDTO(DTOBase):
    total: int = 0
    today_increase: Annotated[int, deprecated] = 0


class StatisticsDTO(DTOBase):
    all_candidates: StatisticsContainerDTO = Field(default_factory=StatisticsContainerDTO)
    delegated_candidates: StatisticsContainerDTO = Field(default_factory=StatisticsContainerDTO)
    platform_candidates: StatisticsContainerDTO = Field(default_factory=StatisticsContainerDTO)


class VacancyResponseStatisticsDTO(StatisticsDTO): ...


class VacancyStageDTO(DTOBase):
    kind: common_dto.VacancyColumnEnum
    shown: bool = True


class PublicationStatusDTO(DTOBase):
    state: PublicationStatusEnum
    url: str | None


class PublicationDTO(DTOBase):
    hh: PublicationStatusDTO
    avito: PublicationStatusDTO


class VacancyResponseDTO(DTOBase):
    id: VacancyID
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
    salary: SalaryAmountRangeDTO | None

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

    tariff: TariffDTO
    statistics: VacancyResponseStatisticsDTO
    stages: list[VacancyStageDTO]

    threshold: float

    @staticmethod
    def from_domain(vacancy: Vacancy) -> "VacancyResponseDTO":
        return VacancyResponseDTO(
            id=vacancy.id,
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
            salary=SalaryAmountRangeDTO(
                currency=vacancy.salary.currency,
                min=vacancy.salary.min,
                max=vacancy.salary.max,
            )
            if vacancy.salary is not None
            else None,
            skills=[s.title for s in vacancy.skills],
            statistics=VacancyResponseStatisticsDTO(
                all_candidates=StatisticsContainerDTO(
                    total=vacancy.statistics.total_candidates,
                    today_increase=0,
                ),
                platform_candidates=StatisticsContainerDTO(
                    total=vacancy.statistics.platform_candidates,
                    today_increase=0,
                ),
                delegated_candidates=StatisticsContainerDTO(
                    total=vacancy.statistics.delegated_candidates,
                    today_increase=0,
                ),
            ),
            is_internship=vacancy.is_internship,
            is_temphire=vacancy.is_temphire,
            daily_rate=vacancy.daily_rate,
            work_format=vacancy.work_format,
            tariff=TariffDTO(title="", analysis_total=0, analysis_used=0),
            stages=[VacancyStageDTO(kind=stage.stage, shown=stage.shown) for stage in vacancy.stages],
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


class GetAllVacanciesResponseDTO(DTOBase):
    vacancies: list[VacancyResponseDTO]


class PublishToDTO(DTOBase):
    hh: bool = False
    # add more platforms when needed


class PostCriterionDTO(DTOBase):
    criterion: str
    initial_weight: int = Field(ge=0)


class PostVacancyRequestPostCriterionDTO(PostCriterionDTO): ...


class PostStopFactorDTO(DTOBase):
    stop_factor: str
    initial_weight: int = Field(ge=0, le=100)


class PostVacancyRequestPostStopFactorDTO(PostStopFactorDTO): ...


class PostVacancyRequestDTO(DTOBase):
    project_id: ProjectID
    title: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1, max_length=15000)
    specialization: str = Field(min_length=1, max_length=500)
    status: VacancyStatus | None = None
    city: str | None = Field(max_length=100, default=None)
    country: str | None = Field(max_length=100, default=None)
    hire_amount: int | None = None
    salary: SalaryAmountRangeDTO | None = None
    work_type: WorkTypeEnum | None = None
    work_format: list[WorkFormatEnum] | None = None
    is_internship: bool | None = None
    is_temphire: bool | None = None
    schedule: list[ScheduleEnum] | None = None
    daily_rate: list[int] | None = None
    experience: ExperienceEnum | None = None
    skills: list[str]
    stages: list[VacancyStageDTO] | None = None
    publish_to: PublishToDTO | None = None
    criteria: list[PostVacancyRequestPostCriterionDTO] | None = None
    stop_factors: list[PostVacancyRequestPostStopFactorDTO] | None = None
    threshold: float = Field(ge=0, le=1)


class PutCriterionDTO(DTOBase):
    id: CriterionID
    initial_weight: int = Field(ge=0)


class PutStopFactorDTO(DTOBase):
    id: StopFactorID
    initial_weight: int = Field(ge=0, le=100)


class PutVacancyRequestDTO(DTOBase):
    title: str | None = Field(min_length=1, max_length=150, default=None)
    description: str | None = Field(min_length=1, max_length=15000, default=None)
    specialization: str | None = Field(min_length=1, max_length=500, default=None)
    thumbnail_url: str | None = None
    status: VacancyStatus | None = None
    city: str | None = Field(max_length=100, default=None)
    country: str | None = Field(max_length=100, default=None)
    hire_amount: int | None = None
    salary: SalaryAmountRangeDTO | None = None
    work_type: WorkTypeEnum | None = None
    work_format: list[WorkFormatEnum] | None = None
    is_internship: bool | None = None
    is_temphire: bool | None = None
    schedule: list[ScheduleEnum] | None = None
    daily_rate: list[int] | None = None
    experience: ExperienceEnum | None = None
    skills: list[str] | None = None
    stages: list[VacancyStageDTO] | None = None
    threshold: float | None = Field(ge=0, le=1, default=None)
    limit_maximum: int | None = Field(ge=0, default=None)
    # Пока нельзя обновлять критерии и стоп-факторы
    # put_criteria: list[PutCriterionDTO] | None = None
    # put_stop_factors: list[PutStopFactorDTO] | None = None
    # post_criteria: list[PostCriterionDTO] | None = None
    # post_stop_factors: list[PostStopFactorDTO] | None = None

    def to_update_value(self, user_id: UserID, vacancy_id: VacancyID) -> VacancyRichUpdateHook.RichUpdateVacancyRequest:
        update_salary: UpdateValue[SalaryAmountRange | None] | None = None
        if "salary" in self.model_fields_set:
            if self.salary is None:
                update_salary = UpdateValue(None)
            else:
                update_salary = UpdateValue(
                    SalaryAmountRange(
                        currency=self.salary.currency,
                        min=self.salary.min,
                        max=self.salary.max,
                    )
                )

        return VacancyRichUpdateHook.RichUpdateVacancyRequest(
            user_id=user_id,
            vacancy_id=vacancy_id,
            salary=update_salary,
            hire_amount=UpdateValue(self.hire_amount) if "hire_amount" in self.model_fields_set else None,
            country=UpdateValue(self.country) if "country" in self.model_fields_set else None,
            city=UpdateValue(self.city) if "city" in self.model_fields_set else None,
            title=UpdateValue(self.title) if self.title is not None else None,
            description=UpdateValue(self.description) if self.description is not None else None,
            specialization=UpdateValue(self.specialization) if self.specialization is not None else None,
            status=UpdateValue(self.status) if self.status is not None else None,
            thumbnail_url=UpdateValue(self.thumbnail_url) if self.thumbnail_url is not None else None,
            work_type=UpdateValue(self.work_type) if self.work_type is not None else None,
            work_format=UpdateValue(self.work_format) if self.work_format is not None else None,
            is_internship=UpdateValue(self.is_internship) if self.is_internship is not None else None,
            is_temphire=UpdateValue(self.is_temphire) if self.is_temphire is not None else None,
            schedule=UpdateValue(self.schedule) if self.schedule is not None else None,
            daily_rate=UpdateValue(self.daily_rate) if self.daily_rate is not None else None,
            experience=UpdateValue(self.experience) if self.experience is not None else None,
            threshold=UpdateValue(self.threshold) if self.threshold is not None else None,
            skills=UpdateValue([Skill(title=skill) for skill in self.skills]) if self.skills is not None else None,
            stages=UpdateValue([VacancyStageStatus(stage=stage.kind, shown=stage.shown) for stage in self.stages])
            if self.stages is not None
            else None,
            limit_maximum=self.limit_maximum,
            # Пока нельзя обновлять критерии и стоп-факторы
            # put_criteria=[
            #     VacancyHookService.UpdateCriterionRequest(
            #         id=put_criterion.id,
            #         initial_weight=put_criterion.initial_weight,
            #     )
            #     for put_criterion in self.put_criteria
            # ]
            # if self.put_criteria
            # else None,
            # put_stop_factors=[
            #     VacancyHookService.UpdateStopFactorRequest(
            #         id=put_stop_factor.id,
            #         initial_weight=put_stop_factor.initial_weight,
            #     )
            #     for put_stop_factor in self.put_stop_factors
            # ]
            # if self.put_stop_factors
            # else None,
            # post_criteria=[
            #     VacancyHookService.CreateCriterionRequest(
            #         criterion=post_criterion.criterion,
            #         initial_weight=post_criterion.initial_weight,
            #     )
            #     for post_criterion in self.post_criteria
            # ]
            # if self.post_criteria
            # else None,
            # post_stop_factors=[
            #     VacancyHookService.CreateStopFactorRequest(
            #         stop_factor=post_stop_factor.stop_factor,
            #         initial_weight=post_stop_factor.initial_weight,
            #     )
            #     for post_stop_factor in self.post_stop_factors
            # ]
            # if self.post_stop_factors
            # else None,
        )


class ImportVacancyRequestDTO(DTOBase):
    url: HttpUrl


class ImportVacancyResponseDTO(DTOBase):
    title: str
    description: str
    specialization: str
    status: VacancyStatus
    city: str | None
    country: str | None
    hire_amount: int | None
    salary: SalaryAmountRangeDTO | None
    work_type: WorkTypeEnum
    work_format: list[WorkFormatEnum]
    is_internship: bool
    is_temphire: bool
    schedule: list[ScheduleEnum]
    daily_rate: list[int]
    experience: ExperienceEnum
    skills: list[str]

    @staticmethod
    def from_service(vacancy: VacancyImporterProtocol.ImportVacancyResponse) -> "ImportVacancyResponseDTO":
        return ImportVacancyResponseDTO(
            status=vacancy.status,
            title=vacancy.title,
            description=vacancy.description,
            specialization=vacancy.specialization,
            hire_amount=vacancy.hire_amount,
            city=vacancy.city,
            country=vacancy.country,
            schedule=vacancy.schedule,
            work_type=vacancy.work_type,
            experience=vacancy.experience,
            salary=SalaryAmountRangeDTO(
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
        )


class AddVacancyPublicationRequestDTO(DTOBase):
    url: HttpUrl


class VacancyPublicationPreviewDTO(DTOBase):
    title: str
    count: int
    city: str | None
    published_until: date
