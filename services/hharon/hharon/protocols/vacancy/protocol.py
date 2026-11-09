from abc import ABC, abstractmethod
from dataclasses import dataclass

from hharon.pkg import hhapi


class GetVacancyByIDError(Exception):
    pass


class GetVacancyByIDAccessDeniedError(GetVacancyByIDError):
    """Raised when vacancy is private and user has no access."""


class GetVacancyByIDProtocol(ABC):
    @dataclass
    class GetVacancyByIDRequest:
        access_token: str | None
        vacancy_id: str

    @abstractmethod
    async def get_vacancy_by_id(
        self, request: GetVacancyByIDRequest
    ) -> hhapi.VacanciesVacancyForApplicant | hhapi.VacanciesVacancyForManager: ...
