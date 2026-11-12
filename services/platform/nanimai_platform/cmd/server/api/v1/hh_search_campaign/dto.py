# mypy: disable-error-code="misc"
# ^^^ mypy не умеет работать с динамическими енамами
from __future__ import annotations

from datetime import datetime
from enum import Enum, IntEnum
from typing import Literal, Self

from pydantic import Field, model_validator

import nanimai_platform.external_clients.hharon.hharon_api.v1 as hharon_api
from nanimai_platform.cmd.server.utils.dtobase import DTOBase
from nanimai_platform.domain.scalar.scalars import VacancyID

type StatusDTO = Literal["not_exist", "active", "completed", "failed"]


def generate_options[T: IntEnum](enum: type[T]) -> list[tuple[str, str]]:
    return [(g.name, g.name.lower()) for g in enum if g.value != 0]


FieldEnumDTO = Enum(
    "FieldEnumDTO",
    generate_options(hharon_api.GetHeadhunterSuggestionsRequestField),
)
ResumeSearchLogicDTO = Enum(
    "ResumeSearchLogicDTO",
    generate_options(hharon_api.ResumeSearchLogic),
)
ResumeSearchFieldsDTO = Enum(
    "ResumeSearchFieldsDTO",
    generate_options(hharon_api.ResumeSearchFields),
)
ResumeSearchExperiencePeriodDTO = Enum(
    "ResumeSearchExperiencePeriodDTO",
    generate_options(hharon_api.ResumeSearchExperiencePeriod),
)
SearchCampaignFullTextFilterSettingsCompanySizeDTO = Enum(
    "SearchCampaignFullTextFilterSettingsCompanySizeDTO",
    generate_options(hharon_api.SearchCampaignFullTextFilterSettingsCompanySize),
)
ResumeSearchRelocationDTO = Enum(
    "ResumeSearchRelocationDTO",
    generate_options(hharon_api.ResumeSearchRelocation),
)
EmploymentDTO = Enum(
    "EmploymentDTO",
    generate_options(hharon_api.Employment),
)
ExperienceDTO = Enum(
    "ExperienceDTO",
    generate_options(hharon_api.Experience),
)
GenderDTO = Enum(
    "GenderDTO",
    generate_options(hharon_api.Gender),
)
ResumeSearchLabelDTO = Enum(
    "ResumeSearchLabelDTO",
    generate_options(hharon_api.ResumeSearchLabel),
)
LanguageLevelDTO = Enum(
    "LanguageLevelDTO",
    generate_options(hharon_api.LanguageLevel),
)
CurrencyDTO = Enum(
    "CurrencyDTO",
    generate_options(hharon_api.Currency),
)
ScheduleDTO = Enum(
    "ScheduleDTO",
    generate_options(hharon_api.Schedule),
)
DriverLicenseTypesDTO = Enum(
    "DriverLicenseTypesDTO",
    generate_options(hharon_api.DriverLicenseTypes),
)
JobSearchStatusesEmployerDTO = Enum(
    "JobSearchStatusesEmployerDTO",
    generate_options(hharon_api.JobSearchStatusesEmployer),
)
EducationLevelDTO = Enum(
    "EducationLevelDTO",
    generate_options(hharon_api.EducationLevel),
)
BusinessTripReadinessDTO = Enum(
    "BusinessTripReadinessDTO",
    generate_options(hharon_api.BusinessTripReadiness),
)
EmploymentFormDTO = Enum(
    "EmploymentFormDTO",
    generate_options(hharon_api.EmploymentForm),
)
WorkFormatDTO = Enum(
    "WorkFormatDTO",
    generate_options(hharon_api.WorkFormat),
)
WorkScheduleByDaysDTO = Enum(
    "WorkScheduleByDaysDTO",
    generate_options(hharon_api.WorkScheduleByDays),
)
WorkingHoursDTO = Enum(
    "WorkingHoursDTO",
    generate_options(hharon_api.WorkingHours),
)


class GetHHSuggestionRequestDTO(DTOBase):
    field: FieldEnumDTO
    text: str


class GetHHSuggestionResponseDTO(DTOBase):
    id: str
    text: str


class GetHHSuggestionsListResponseDTO(DTOBase):
    items: list[GetHHSuggestionResponseDTO]


class SearchCampaignSettingsDTO(DTOBase):
    # Квота на количество кандидатов в день
    daily_limit: int
    # Сколько дней вести поиск
    duration_days: int


class SaveHHSearchCampaignSettingsRequestDTO(DTOBase):
    vacancy_id: VacancyID
    payload: SearchCampaignPayloadDTO
    settings: SearchCampaignSettingsDTO


class SaveHHSearchCampaignSettingsResponseDTO(DTOBase):
    status: StatusDTO


class GetSearchCampaignPreviewRequestDTO(DTOBase):
    payload: SearchCampaignPayloadDTO = Field(description="Фильтры поиска")
    settings: SearchCampaignSettingsDTO = Field(description="Настройки кампании")


class GetSearchCampaignPreviewResponseDTO(DTOBase):
    total_candidates: int = Field(description="Всего кандидатов по фильтрам")
    interval_seconds: int = Field(description="Интервал между запусками в секундах")
    candidates_per_run: int = Field(description="Кандидатов за один запуск")


class GetSearchCampaignSettingsResponseDTO(DTOBase):
    payload: SearchCampaignPayloadDTO = Field(description="Параметры поиска")
    settings: SearchCampaignSettingsDTO = Field(description="Настройки кампании")


# Nested DTOs for SearchCampaign filters
class SearchCampaignFullTextFilterSettingsDTO(DTOBase):
    logic: ResumeSearchLogicDTO | None = Field(default=None, description="Логика поиска")
    field: ResumeSearchFieldsDTO | None = Field(default=None, description="Поле для поиска")
    period: ResumeSearchExperiencePeriodDTO | None = Field(default=None, description="Период опыта работы")
    company_size: SearchCampaignFullTextFilterSettingsCompanySizeDTO | None = Field(
        default=None, description="Размер компании"
    )


class SearchCampaignFullTextFilterDTO(DTOBase):
    text: str = Field(description="Поисковая фраза")
    settings: SearchCampaignFullTextFilterSettingsDTO | None = Field(default=None, description="Настройки фильтрации")


class SearchCampaignAgeFilterDTO(DTOBase):
    min: int | None = Field(description="Минимальный возраст")
    max: int | None = Field(description="Максимальный возраст")

    @model_validator(mode="after")
    def validate_min_max(self) -> Self:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("Minimum salary cannot be greater than maximum salary")
        return self


class SearchCampaignAreaFilterDTO(DTOBase):
    area_ids: list[str] = Field(default_factory=list, description="ID регионов")
    relocation: ResumeSearchRelocationDTO | None = Field(default=None, description="Готовность к переезду")


class SearchCampaignDateFilterDateRangeDTO(DTOBase):
    min: datetime | None = Field(default=None, description="Дата начала поиска")
    max: datetime | None = Field(default=None, description="Дата окончания поиска")


class SearchCampaignDateFilterDTO(DTOBase):
    days: int | None = Field(default=None, description="Период в днях")
    date_range: SearchCampaignDateFilterDateRangeDTO | None = Field(default=None, description="Временной промежуток")


class SearchCampaignLanguageFilterDTO(DTOBase):
    language_id: str = Field(description="ID языка")
    level: LanguageLevelDTO = Field(description="Уровень владения языком")


class SearchCampaignSalaryFilterDTO(DTOBase):
    currency: CurrencyDTO = Field(description="Код валюты")
    min: int | None = Field(description="Минимальная ЗП")
    max: int | None = Field(description="Максимальная ЗП")

    @model_validator(mode="after")
    def validate_min_max(self) -> Self:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("Minimum salary cannot be greater than maximum salary")
        return self


class SearchCampaignExperienceIndustryFilterDTO(DTOBase):
    industry_ids: list[str] = Field(default_factory=list, description="ID отраслей")
    period: ResumeSearchExperiencePeriodDTO | None = Field(default=None, description="Период опыта работы")


class SearchCampaignPayloadDTO(DTOBase):
    text: list[SearchCampaignFullTextFilterDTO] = Field(default_factory=list, description="Фильтры по тексту")
    age: SearchCampaignAgeFilterDTO | None = Field(default=None, description="Фильтр по возрасту")
    area: SearchCampaignAreaFilterDTO | None = Field(default=None, description="Фильтр по регионам")
    date: SearchCampaignDateFilterDTO | None = Field(default=None, description="Фильтр по дате публикации")
    employment: list[EmploymentDTO] = Field(default_factory=list, description="Типы занятости")
    experience: list[ExperienceDTO] = Field(default_factory=list, description="Опыт работы")
    skill_ids: list[str] = Field(default_factory=list, description="ID навыков")
    gender: GenderDTO | None = Field(default=None, description="Пол соискателя")
    label: list[ResumeSearchLabelDTO] = Field(default_factory=list, description="Лейблы резюме")
    language: list[SearchCampaignLanguageFilterDTO] = Field(default_factory=list, description="Фильтр по языкам")
    metro_ids: list[str] = Field(default_factory=list, description="ID станций метро")
    salary: SearchCampaignSalaryFilterDTO | None = Field(default=None, description="Фильтр по зарплате")
    schedule: list[ScheduleDTO] = Field(default_factory=list, description="График работы")
    citizenship_ids: list[str] = Field(default_factory=list, description="Гражданство")
    work_ticket_ids: list[str] = Field(default_factory=list, description="Разрешение на работу")
    educational_institution_ids: list[str] = Field(default_factory=list, description="ID учебных заведений")
    search_in_responses: bool = Field(default=False, description="Поиск в откликах")
    by_text_prefix: bool = Field(default=False, description="Поиск по префиксу")
    driver_license_types: list[DriverLicenseTypesDTO] = Field(default_factory=list, description="Водительские права")
    professional_role_ids: list[str] = Field(default_factory=list, description="ID профессиональных ролей")
    district_ids: list[str] = Field(default_factory=list, description="ID районов")
    job_search: list[JobSearchStatusesEmployerDTO] = Field(default_factory=list, description="Статусы поиска работы")
    education_levels: list[EducationLevelDTO] = Field(default_factory=list, description="Уровень образования")
    business_trip_readiness: list[BusinessTripReadinessDTO] = Field(
        default_factory=list, description="Готовность к командировкам"
    )
    experience_industry: SearchCampaignExperienceIndustryFilterDTO | None = Field(
        default=None, description="Опыт работы в отрасли"
    )

    @classmethod
    def from_proto(cls, campaign: hharon_api.SearchCampaign) -> SearchCampaignPayloadDTO:
        """Convert gRPC SearchCampaign to DTO."""
        return cls(
            text=[
                SearchCampaignFullTextFilterDTO(
                    text=t.text,
                    settings=SearchCampaignFullTextFilterSettingsDTO(
                        logic=ResumeSearchLogicDTO[t.settings.logic.name] if t.settings.logic.value != 0 else None,
                        field=ResumeSearchFieldsDTO[t.settings.field.name] if t.settings.field.value != 0 else None,
                        period=ResumeSearchExperiencePeriodDTO[t.settings.period.name]
                        if t.settings.period.value != 0
                        else None,
                        company_size=SearchCampaignFullTextFilterSettingsCompanySizeDTO[t.settings.company_size.name]
                        if t.settings.company_size.value != 0
                        else None,
                    )
                    if t.settings
                    else None,
                )
                for t in campaign.text
            ],
            age=SearchCampaignAgeFilterDTO(
                min=campaign.age.min if campaign.age.min > 0 else None,
                max=campaign.age.max if campaign.age.max > 0 else None,
            )
            if campaign.age
            else None,
            area=SearchCampaignAreaFilterDTO(
                area_ids=list(campaign.area.area_ids),
                relocation=ResumeSearchRelocationDTO[campaign.area.relocation.name]
                if campaign.area.relocation and campaign.area.relocation.value != 0
                else None,
            )
            if campaign.area
            else None,
            date=SearchCampaignDateFilterDTO(
                days=campaign.date.days if campaign.date and campaign.date.days is not None else None,
                date_range=SearchCampaignDateFilterDateRangeDTO(
                    min=campaign.date.date_range.min if campaign.date.date_range else None,
                    max=campaign.date.date_range.max if campaign.date.date_range else None,
                )
                if campaign.date and campaign.date.date_range
                else None,
            )
            if campaign.date
            else None,
            employment=[EmploymentDTO[e.name] for e in campaign.employment if e.value != 0],
            experience=[ExperienceDTO[e.name] for e in campaign.experience if e.value != 0],
            skill_ids=list(campaign.skill_ids),
            gender=GenderDTO[campaign.gender.name] if campaign.gender and campaign.gender.value != 0 else None,
            label=[ResumeSearchLabelDTO[lbl.name] for lbl in campaign.label if lbl.value != 0],
            language=[
                SearchCampaignLanguageFilterDTO(language_id=lang.language_id, level=LanguageLevelDTO[lang.level.name])
                for lang in campaign.language
            ],
            metro_ids=list(campaign.metro_ids),
            salary=SearchCampaignSalaryFilterDTO(
                currency=CurrencyDTO[campaign.salary.currency.name],
                min=campaign.salary.min if campaign.salary.min > 0 else None,
                max=campaign.salary.max if campaign.salary.max > 0 else None,
            )
            if campaign.salary
            else None,
            schedule=[ScheduleDTO[s.name] for s in campaign.schedule if s.value != 0],
            citizenship_ids=list(campaign.citizenship_ids),
            work_ticket_ids=list(campaign.work_ticket_ids),
            educational_institution_ids=list(campaign.educational_institution_ids),
            search_in_responses=campaign.search_in_responses,
            by_text_prefix=campaign.by_text_prefix,
            driver_license_types=[DriverLicenseTypesDTO[d.name] for d in campaign.driver_license_types if d.value != 0],
            professional_role_ids=list(campaign.professional_role_ids),
            district_ids=list(campaign.district_ids),
            job_search=[JobSearchStatusesEmployerDTO[j.name] for j in campaign.job_search if j.value != 0],
            education_levels=[EducationLevelDTO[e.name] for e in campaign.education_levels if e.value != 0],
            business_trip_readiness=[
                BusinessTripReadinessDTO[b.name] for b in campaign.business_trip_readiness if b.value != 0
            ],
            experience_industry=SearchCampaignExperienceIndustryFilterDTO(
                industry_ids=list(campaign.experience_industry.industry_ids),
                period=ResumeSearchExperiencePeriodDTO[campaign.experience_industry.period.name]
                if campaign.experience_industry.period and campaign.experience_industry.period.value != 0
                else None,
            )
            if campaign.experience_industry
            else None,
        )

    def to_proto(self) -> hharon_api.SearchCampaign:
        """Convert DTO to gRPC SearchCampaign."""
        return hharon_api.SearchCampaign(
            text=[
                hharon_api.SearchCampaignFullTextFilter(
                    text=t.text,
                    settings=hharon_api.SearchCampaignFullTextFilterSettings(
                        logic=hharon_api.ResumeSearchLogic[t.settings.logic.name]
                        if t.settings and t.settings.logic
                        else hharon_api.ResumeSearchLogic(0),
                        field=hharon_api.ResumeSearchFields[t.settings.field.name]
                        if t.settings and t.settings.field
                        else hharon_api.ResumeSearchFields(0),
                        period=hharon_api.ResumeSearchExperiencePeriod[t.settings.period.name]
                        if t.settings and t.settings.period
                        else hharon_api.ResumeSearchExperiencePeriod(0),
                        company_size=hharon_api.SearchCampaignFullTextFilterSettingsCompanySize[
                            t.settings.company_size.name
                        ]
                        if t.settings and t.settings.company_size
                        else hharon_api.SearchCampaignFullTextFilterSettingsCompanySize(0),
                    )
                    if t.settings
                    else None,
                )
                for t in self.text
            ],
            age=hharon_api.SearchCampaignAgeFilter(min=self.age.min or 0, max=self.age.max or 0) if self.age else None,
            area=hharon_api.SearchCampaignAreaFilter(
                area_ids=self.area.area_ids,
                relocation=hharon_api.ResumeSearchRelocation[self.area.relocation.name]
                if self.area.relocation
                else hharon_api.ResumeSearchRelocation(0),
            )
            if self.area
            else None,
            date=hharon_api.SearchCampaignDateFilter(
                days=self.date.days if self.date.days is not None else None,
                date_range=hharon_api.SearchCampaignDateFilterDateRange(
                    min=self.date.date_range.min, max=self.date.date_range.max
                )
                if self.date.date_range
                else None,
            )
            if self.date
            else None,
            employment=[hharon_api.Employment[e.name] for e in self.employment],
            experience=[hharon_api.Experience[e.name] for e in self.experience],
            skill_ids=self.skill_ids,
            gender=hharon_api.Gender[self.gender.name] if self.gender else hharon_api.Gender(0),
            label=[hharon_api.ResumeSearchLabel[lbl.name] for lbl in self.label],
            language=[
                hharon_api.SearchCampaignLanguageFilter(
                    language_id=lang.language_id,
                    level=hharon_api.LanguageLevel[lang.level.name],
                )
                for lang in self.language
            ],
            metro_ids=self.metro_ids,
            salary=hharon_api.SearchCampaignSalaryFilter(
                currency=hharon_api.Currency[self.salary.currency.name],
                min=self.salary.min or 0,
                max=self.salary.max or 0,
            )
            if self.salary
            else None,
            schedule=[hharon_api.Schedule[s.name] for s in self.schedule],
            citizenship_ids=self.citizenship_ids,
            work_ticket_ids=self.work_ticket_ids,
            educational_institution_ids=self.educational_institution_ids,
            search_in_responses=self.search_in_responses,
            by_text_prefix=self.by_text_prefix,
            driver_license_types=[hharon_api.DriverLicenseTypes[d.name] for d in self.driver_license_types],
            professional_role_ids=self.professional_role_ids,
            district_ids=self.district_ids,
            job_search=[hharon_api.JobSearchStatusesEmployer[j.name] for j in self.job_search],
            education_levels=[hharon_api.EducationLevel[e.name] for e in self.education_levels],
            business_trip_readiness=[hharon_api.BusinessTripReadiness[b.name] for b in self.business_trip_readiness],
            experience_industry=hharon_api.SearchCampaignExperienceIndustryFilter(
                industry_ids=self.experience_industry.industry_ids,
                period=hharon_api.ResumeSearchExperiencePeriod[self.experience_industry.period.name]
                if self.experience_industry.period
                else hharon_api.ResumeSearchExperiencePeriod(0),
            )
            if self.experience_industry
            else None,
        )


class GetStatusResponseDTO(DTOBase):
    status: StatusDTO = Field(
        description="Статус поисковой кампании",
    )

    active_until: datetime | None = Field(
        description="Дата и время окончания активности поисковой кампании.",
    )

    collected_current: int | None = Field(
        description="Текущее количество кандидатов найденных сегодня в рамках кампании."
    )

    collected_maximum: int | None = Field(
        description="Максимальное количество кандидатов, которое может быть найдено сегодня в рамках кампании."
    )


class PostStopResponseDTO(DTOBase):
    status: StatusDTO = Field(
        description="Статус поисковой кампании",
    )


class PostStartResponseDTO(DTOBase):
    status: StatusDTO = Field(
        description="Статус поисковой кампании",
    )


class GetAccessResponseDTO(DTOBase):
    has_access: bool = Field(description="Флаг, указывающий, есть ли доступ к поиску резюме")
    account_name: str | None = Field(description="Имя пользователя. Пустое, если доступа нет")
    account_email: str | None = Field(description="Email пользователя. Пустое, если доступа нет")
    expires_at: datetime | None = Field(description="Дата истечения доступа")
