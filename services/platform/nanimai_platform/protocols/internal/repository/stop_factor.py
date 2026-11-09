from abc import ABC, abstractmethod
from dataclasses import dataclass

from nanimai_platform.domain import ProjectID, StopFactor, StopFactorID, StopFactorPayload, UserID, VacancyID


class StopFactorRepositoryError(Exception): ...


class StopFactorValidateError(StopFactorRepositoryError): ...


class StopFactorNotFoundError(StopFactorRepositoryError): ...


class CreateStopFactorError(StopFactorRepositoryError): ...


class ReadStopFactorError(StopFactorRepositoryError): ...


class UpdateStopFactorError(StopFactorRepositoryError): ...


class DeleteStopFactorError(StopFactorRepositoryError): ...


class StopFactorRepositoryProtocol(ABC):
    @dataclass
    class CreateStopFactorRequest:
        user_id: UserID
        project_id: ProjectID
        vacancy_id: VacancyID
        stop_factor: str
        initial_weight: int

    @abstractmethod
    async def create_stop_factor(self, request: CreateStopFactorRequest) -> StopFactor:
        """creates stop-factor in repository

        Raises:
            CreateStopFactorError - not expected exception
            StopFactorValidateError - validation error
            VacancyNotFoundError - vacancy not found
        Returns:
            StopFactor - created stop-factor
        """
        ...

    @dataclass
    class CreateManyStopFactorsRequest:
        user_id: UserID
        project_id: ProjectID
        vacancy_id: VacancyID
        stop_factors: list[StopFactorPayload]

    @abstractmethod
    async def create_many_stop_factors(self, request: CreateManyStopFactorsRequest) -> list[StopFactorID]:
        """creates many stop-factors in repository

        Raises:
            CreateStopFactorError - not expected exception
            StopFactorValidateError - validation error
            VacancyNotFoundError - vacancy not found
        Returns:
            StopFactorID - ids of created stop-factors
        """
        ...

    @dataclass
    class ReadStopFactorRequest:
        id: StopFactorID

    @abstractmethod
    async def read_stop_factor(self, request: ReadStopFactorRequest) -> StopFactor:
        """reads stop-factor in repository

        Raises:
            ReadStopFactorError - not expected exception
            StopFactorValidateError - validation error
            StopFactorNotFoundError - stop-factor not found
        Returns:
            StopFactor - read stop_factor
        """
        ...

    @dataclass
    class UpdateStopFactorRequest:
        id: StopFactorID

        stop_factor: str | None = None
        initial_weight: int | None = None

    @abstractmethod
    async def update_stop_factor(self, request: UpdateStopFactorRequest) -> StopFactor:
        """update stop-factor in repository

        Raises:
            UpdateStopFactorError - not expected exception
            StopFactorValidateError - validation error
            StopFactorNotFoundError - stop-factor not found
        Returns:
            StopFactor - updated stop-factor
        """
        ...

    @dataclass
    class DeleteStopFactorRequest:
        id: StopFactorID

    @abstractmethod
    async def delete_stop_factor(self, request: DeleteStopFactorRequest) -> StopFactor:
        """deletes stop-factor in repository

        Raises:
            DeleteStopFactorError - not expected exception
            StopFactorValidateError - validation error
            StopFactorNotFoundError -stop-factor not found
        Returns:
            StopFactor - deleted stop_factor
        """
        ...

    @dataclass
    class ReadManyStopFactorsRequest:
        stop_factor_ids: list[StopFactorID]

    @abstractmethod
    async def read_many_stop_factors(self, request: ReadManyStopFactorsRequest) -> list[StopFactor | None]:
        """reads many stop_factors in repository

        Raises:
            ReadStopFactorError - not expected exception
            StopFactorValidateError - validation error
        Returns:
            list[StopFactor | None] - list of stop_factors or None if stop-factor does not exist
        """
        ...

    @dataclass
    class ReadManyStopFactorsByVacancyRequest:
        vacancy_id: VacancyID

    @abstractmethod
    async def read_many_stop_factors_by_vacancy(self, request: ReadManyStopFactorsByVacancyRequest) -> list[StopFactor]:
        """reads many stop_factors by vacancy in repository

        Raises:
            ReadStopFactorError - not expected exception
            StopFactorValidateError - validation error
        Returns:
            list[StopFactor] - list of stop_factors
        """
        ...
