from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from nanimai_platform.domain import (
    CandidateID,
    ExperienceEnum,
    ProjectID,
    SalaryAmountRange,
    ScheduleEnum,
    Skill,
    UserID,
    Vacancy,
    VacancyID,
    VacancyPublication,
    VacancyStageStatus,
    VacancyStatus,
    WorkFormatEnum,
    WorkTypeEnum,
)
from nanimai_platform.domain.vacancy.vacancy import VacancyPublicationSourceEnum, VacancyStatistics
from nanimai_platform.utils.update_value import UpdateValue


class VacancyRepositoryError(Exception): ...


class VacancyValidateError(VacancyRepositoryError): ...


class VacancyNotFoundError(VacancyRepositoryError): ...


class CreateVacancyError(VacancyRepositoryError): ...


class ReadVacancyError(VacancyRepositoryError): ...


class UpdateVacancyError(VacancyRepositoryError): ...


class DeleteVacancyError(VacancyRepositoryError): ...


class VacancyRepositoryProtocol(ABC):
    @dataclass
    class CreateVacancyRequest:
        user_id: UserID
        project_id: ProjectID
        title: str
        description: str
        specialization: str
        thumbnail_url: str
        status: VacancyStatus
        city: str | None
        country: str | None
        hire_amount: int | None
        salary: SalaryAmountRange | None
        work_type: WorkTypeEnum
        work_format: list[WorkFormatEnum]
        is_internship: bool
        is_temphire: bool
        schedule: list[ScheduleEnum]
        daily_rate: list[int]
        experience: ExperienceEnum
        skills: list[Skill]
        stages: list[VacancyStageStatus]
        publication: VacancyPublication
        candidates: list[CandidateID]
        statistics: VacancyStatistics
        threshold: float

    @abstractmethod
    async def create_vacancy(self, request: CreateVacancyRequest) -> Vacancy:
        """creates vacancy in repository

        Raises:
            CreateVacancyError - not expected exception
            VacancyValidateError - validation error
        Returns:
            Vacancy - created vacancy
        """
        ...

    @dataclass
    class ReadVacancyRequest:
        id: VacancyID

    @abstractmethod
    async def read_vacancy(self, request: ReadVacancyRequest) -> Vacancy:
        """reads vacancy in repository

        Raises:
            ReadVacancyError - not expected exception
            VacancyValidateError - validation error
            VacancyNotFoundError - vacancy not found
        Returns:
            Vacancy - read vacancy
        """
        ...

    @dataclass
    class UpdateVacancyRequest:
        id: VacancyID

        title: UpdateValue[str] | None = None
        description: UpdateValue[str] | None = None
        specialization: UpdateValue[str] | None = None
        thumbnail_url: UpdateValue[str] | None = None
        status: UpdateValue[VacancyStatus] | None = None
        city: UpdateValue[str | None] | None = None
        country: UpdateValue[str | None] | None = None
        hire_amount: UpdateValue[int | None] | None = None
        salary: UpdateValue[SalaryAmountRange | None] | None = None
        work_type: UpdateValue[WorkTypeEnum] | None = None
        work_format: UpdateValue[list[WorkFormatEnum]] | None = None
        is_internship: UpdateValue[bool] | None = None
        is_temphire: UpdateValue[bool] | None = None
        schedule: UpdateValue[list[ScheduleEnum]] | None = None
        daily_rate: UpdateValue[list[int]] | None = None
        experience: UpdateValue[ExperienceEnum] | None = None
        skills: UpdateValue[list[Skill]] | None = None
        stages: UpdateValue[list[VacancyStageStatus]] | None = None
        publication: UpdateValue[VacancyPublication] | None = None
        candidates: UpdateValue[list[CandidateID]] | None = None
        statistics: UpdateValue[VacancyStatistics] | None = None
        threshold: UpdateValue[float] | None = None
        updated_at: UpdateValue[datetime] | None = None

    @abstractmethod
    async def update_vacancy(self, request: UpdateVacancyRequest) -> Vacancy:
        """updates vacancy in repository

        Raises:
            UpdateVacancyError - not expected exception
            VacancyValidateError - validation error
            VacancyNotFoundError - vacancy not found
        Returns:
            Vacancy - updated vacancy
        """
        ...

    @dataclass
    class DeleteVacancyRequest:
        id: VacancyID

    @abstractmethod
    async def delete_vacancy(self, request: DeleteVacancyRequest) -> Vacancy:
        """deletes vacancy in repository

        Raises:
            DeleteVacancyError - not expected exception
            VacancyValidateError - validation error
            VacancyNotFoundError - vacancy not found
        Returns:
            Vacancy - deleted vacancy
        """
        ...

    @dataclass
    class ReadManyVacanciesRequest:
        vacancy_ids: list[VacancyID]

    @abstractmethod
    async def read_many_vacancies(self, request: ReadManyVacanciesRequest) -> list[Vacancy | None]:
        """reads many vacancies in repository

        Raises:
            ReadVacancyError - not expected exception
            VacancyValidateError - validation error
            VacancyNotFoundError - vacancy not found
        Returns:
            list[Vacancy | None] - list of vacancies or None if vacancy does not exist
        """
        ...

    @dataclass
    class ReadManyVacanciesByProjectRequest:
        project_id: ProjectID

    @abstractmethod
    async def read_many_vacancies_by_project(self, request: ReadManyVacanciesByProjectRequest) -> list[Vacancy]:
        """reads many vacancies by project in repository

        Raises:
            ReadVacancyError - not expected exception
            VacancyValidateError - validation error
            ProjectNotFoundError - project not found
        Returns:
            list[Vacancy] - list of vacancies
        """
        ...

    @dataclass
    class ReadManyPublishedVacanciesRequest:
        source: VacancyPublicationSourceEnum

    @abstractmethod
    async def read_many_published_vacancies(self, request: ReadManyPublishedVacanciesRequest) -> list[Vacancy]:
        """reads many published vacancies in repository

        Raises:
            ReadVacancyError - not expected exception
            VacancyValidateError - validation error
        Returns:
            list[Vacancy] - list of vacancies
        """
        ...
