from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl

from nanimai_platform.domain import (
    ExperienceEnum,
    SalaryAmountRange,
    ScheduleEnum,
    Skill,
    UserID,
    VacancyStatus,
    WorkFormatEnum,
    WorkTypeEnum,
)


class VacancyImporterError(Exception): ...


class WrongURLFormatError(VacancyImporterError): ...


class VacancyImporterProtocol(ABC):
    class ImportVacancyRequest(BaseModel):
        url: HttpUrl
        user_id: UserID | None = None

    class ImportVacancyResponse(BaseModel):
        title: str = Field(description="vacancy title")
        description: str = Field(description="vacancy description")
        specialization: str = Field(description="vacancy specialization")
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
        published_at: datetime = Field(description="vacancy published at")

    @abstractmethod
    async def import_vacancy(self, request: ImportVacancyRequest) -> ImportVacancyResponse:
        """Import vacancy from url

        Raises:
            VacancyImporterError - unexpected error
            WrongURLFormatError - url format is not correct (e.g. wrong Url for hh service)
        Returns:
            Vacancy: imported vacancy
        """
        ...

    class GetVacancyIDRequest(BaseModel):
        url: HttpUrl

    class GetVacancyIDResponse(BaseModel):
        vacancy_id: str

    @abstractmethod
    def get_vacancy_id(self, request: GetVacancyIDRequest) -> GetVacancyIDResponse:
        """Gets vacancy id from url

        Raises:
            VacancyImporterError - unexpected error
            WrongURLFormatError - url format is not correct (e.g. wrong Url for hh service)
        Returns:
            GetVacancyIDResponse: vacancy id from url
        """
        ...
