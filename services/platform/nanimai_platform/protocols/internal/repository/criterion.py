from abc import ABC, abstractmethod
from dataclasses import dataclass

from nanimai_platform.domain import Criterion, CriterionID, CriterionPayload, ProjectID, UserID, VacancyID


class CriterionRepositoryError(Exception): ...


class CriterionValidateError(CriterionRepositoryError): ...


class CriterionNotFoundError(CriterionRepositoryError): ...


class CreateCriterionError(CriterionRepositoryError): ...


class ReadCriterionError(CriterionRepositoryError): ...


class UpdateCriterionError(CriterionRepositoryError): ...


class DeleteCriterionError(CriterionRepositoryError): ...


class CriterionRepositoryProtocol(ABC):
    @dataclass
    class CreateCriterionRequest:
        user_id: UserID
        project_id: ProjectID
        vacancy_id: VacancyID
        criterion: str
        initial_weight: int
        weight: float
        calculated: bool

    @abstractmethod
    async def create_criterion(self, request: CreateCriterionRequest) -> Criterion:
        """creates criterion in repository

        Raises:
            CreateCriterionError - not expected exception
            CriterionValidateError - validation error
            VacancyNotFoundError - vacancy not found
        Returns:
            Criterion - created criterion
        """
        ...

    @dataclass
    class CreateManyCriteriaRequest:
        user_id: UserID
        project_id: ProjectID
        vacancy_id: VacancyID
        criteria: list[CriterionPayload]

    @abstractmethod
    async def create_many_criteria(self, request: CreateManyCriteriaRequest) -> list[CriterionID]:
        """creates many criteria in repository

        Raises:
            CreateCriterionError - not expected exception
            CriterionValidateError - validation error
            VacancyNotFoundError - vacancy not found
        Returns:
            CriterionID - ids of created criteria
        """
        ...

    @dataclass
    class ReadCriterionRequest:
        id: CriterionID

    @abstractmethod
    async def read_criterion(self, request: ReadCriterionRequest) -> Criterion:
        """reads criterion in repository

        Raises:
            ReadCriterionError - not expected exception
            CriterionValidateError - validation error
            CriterionNotFoundError - criterion not found
        Returns:
            Criterion - read criterion
        """
        ...

    @dataclass
    class UpdateCriterionRequest:
        id: CriterionID

        criterion: str | None = None
        initial_weight: int | None = None
        weight: float | None = None
        calculated: bool | None = None

    @abstractmethod
    async def update_criterion(self, request: UpdateCriterionRequest) -> Criterion:
        """update criterion in repository

        Raises:
            UpdateCriterionError - not expected exception
            CriterionValidateError - validation error
            CriterionNotFoundError - criterion not found
        Returns:
            Criterion - updated criterion
        """
        ...

    @dataclass
    class DeleteCriterionRequest:
        id: CriterionID

    @abstractmethod
    async def delete_criterion(self, request: DeleteCriterionRequest) -> Criterion:
        """deletes criterion in repository

        Raises:
            DeleteCriterionError - not expected exception
            CriterionValidateError - validation error
            CriterionNotFoundError - criterion not found
        Returns:
            Criterion - deleted criterion
        """
        ...

    @dataclass
    class ReadManyCriteriaRequest:
        criterion_ids: list[CriterionID]

    @abstractmethod
    async def read_many_criteria(self, request: ReadManyCriteriaRequest) -> list[Criterion | None]:
        """reads many criteria in repository

        Raises:
            ReadCriterionError - not expected exception
            CriterionValidateError - validation error
        Returns:
            list[Criterion | None] - list of criteria or None if criterion does not exist
        """
        ...

    @dataclass
    class ReadManyCriteriaByVacancyRequest:
        vacancy_id: VacancyID

    @abstractmethod
    async def read_many_criteria_by_vacancy(self, request: ReadManyCriteriaByVacancyRequest) -> list[Criterion]:
        """reads many criteria by vacancy in repository

        Raises:
            ReadCriterionError - not expected exception
            CriterionValidateError - validation error
        Returns:
            list[Criterion] - list of criteria
        """
        ...
