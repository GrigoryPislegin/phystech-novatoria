from abc import ABC, abstractmethod
from dataclasses import dataclass

from nanimai_platform.domain.project.project import ProjectStatistics
from nanimai_platform.domain.scalar.scalars import (
    ProjectID,
    StatisticsID,
    VacancyID,
)
from nanimai_platform.domain.statistics.statistics import (
    CandidateCriterionStopFactorStatusStatistics,
    CandidateDateIncreaseStatistics,
    CandidateSalaryStatistics,
    CandidateScoreStatistics,
    CandidateStageStatistics,
    Statistics,
    VacancyCandidatesStatistics,
)


class StatisticsRepositoryError(Exception): ...


class StatisticsValidateError(StatisticsRepositoryError): ...


class StatisticsNotFoundError(StatisticsRepositoryError): ...


class StatisticsWithVacancyAlreadyExistsError(StatisticsRepositoryError): ...


class CreateStatisticsError(StatisticsRepositoryError): ...


class ReadStatisticsError(StatisticsRepositoryError): ...


class UpdateStatisticsError(StatisticsRepositoryError): ...


class DeleteStatisticsError(StatisticsRepositoryError): ...


class StatisticsRepositoryProtocol(ABC):
    @dataclass
    class CreateStatisticsRequest:
        vacancy_id: VacancyID

        project_statistics: ProjectStatistics
        vacancy_statistics: VacancyCandidatesStatistics
        score_statistics: CandidateScoreStatistics
        stage_statistics: CandidateStageStatistics
        criterion_stop_factor_status_statistics: CandidateCriterionStopFactorStatusStatistics
        date_increase_statistics: CandidateDateIncreaseStatistics
        salary_statistics: CandidateSalaryStatistics

    @abstractmethod
    async def create_statistics(self, request: CreateStatisticsRequest) -> Statistics:
        """creates statistics in repository

        Raises:
            StatisticsWithVacancyAlreadyExistsError - error if statistics for vacancy already exists
            CreateStatisticsError - not expected exception
            StatisticsValidateError - validation error
            VacancyNotFoundError - vacancy not found
        Returns:
            Statistics - created statistics
        """
        ...

    @dataclass
    class ReadStatisticsByVacancyRequest:
        vacancy_id: VacancyID

    @abstractmethod
    async def read_statistics_by_vacancy(self, request: ReadStatisticsByVacancyRequest) -> Statistics:
        """reads statistics in repository by vacancy

        Raises:
            ReadStatisticsError - not expected exception
            StatisticsValidateError - validation error
            StatisticsNotFoundError - statistics not found
        Returns:
            Statistics - read statistics
        """
        ...

    @dataclass
    class ReadManyStatisticsByProjectRequest:
        project_id: ProjectID

    @abstractmethod
    async def read_many_statistics_by_project(self, request: ReadManyStatisticsByProjectRequest) -> list[Statistics]:
        """reads many statistics in repository by project

        Raises:
            ReadStatisticsError - not expected exception
            StatisticsValidateError - validation error
        Returns:
            list[Statistics] - read many statistics
        """
        ...

    @dataclass
    class UpdateStatisticsByVacancyRequest:
        vacancy_id: VacancyID

        project_statistics: ProjectStatistics | None = None
        vacancy_statistics: VacancyCandidatesStatistics | None = None
        score_statistics: CandidateScoreStatistics | None = None
        stage_statistics: CandidateStageStatistics | None = None
        criterion_stop_factor_status_statistics: CandidateCriterionStopFactorStatusStatistics | None = None
        date_increase_statistics: CandidateDateIncreaseStatistics | None = None
        salary_statistics: CandidateSalaryStatistics | None = None

    @abstractmethod
    async def update_or_create_statistics_by_vacancy(self, request: UpdateStatisticsByVacancyRequest) -> Statistics:
        """update statistics in repository or create new statistics by vacancy

        Raises:
            UpdateStatisticsError - not expected exception
            CreateStatisticsError - not expected exception while creating new statistics
            StatisticsValidateError - validation error
        Returns:
            Statistics - updated statistics
        """
        ...

    @dataclass
    class DeleteStatisticsRequest:
        id: StatisticsID

    @abstractmethod
    async def delete_statistics(self, request: DeleteStatisticsRequest) -> Statistics:
        """deletes statistics in repository

        Raises:
            DeleteStatisticsError - not expected exception
            StatisticsValidateError - validation error
            StatisticsNotFoundError - statistics not found
        Returns:
            Statistics - deleted statistics
        """
        ...

    @dataclass
    class ReadManyStatisticsByVacanciesRequest:
        vacancy_ids: list[VacancyID]

    @abstractmethod
    async def read_many_statistics_by_vacancies(
        self, request: ReadManyStatisticsByVacanciesRequest
    ) -> list[Statistics | None]:
        """reads many statistics in repository by vacancies

        Raises:
            ReadStatisticsError - not expected exception
            StatisticsValidateError - validation error
        Returns:
            list[Criterion] - list of statistics
        """
        ...
