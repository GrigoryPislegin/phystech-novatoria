from collections.abc import AsyncGenerator
from typing import Protocol

from hharon.pkg import hhapi
from hharon.pkg.hhapi.models import Item2, ResumeResumeForEmployer


class ResponseCollectionPreviewHHApiError(Exception): ...


class ResponseCollectionPreviewHHApiNotFoundError(Exception): ...


class ResponseCollectionPreviewHHApiAccessDeniedError(Exception): ...


class ResponseCollectionPreviewHHApiProtocol(Protocol):
    async def get_negotiations(
        self, access_token: str, hh_vacancy_id: str
    ) -> hhapi.NegotiationsNegotiationsCollections: ...

    async def get_vacancies_vacancy_id(
        self, access_token: str, hh_vacancy_id: str
    ) -> hhapi.VacanciesVacancyForManager | hhapi.VacanciesVacancyForApplicant: ...


class HeadHunterResponseCollectionError(Exception):
    """Base exception for HeadHunter response collection errors."""


class HeadHunterRateLimitError(HeadHunterResponseCollectionError):
    """Rate limit error from HeadHunter API."""

    retry_after: int | None

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class HeadHunterAccessDeniedError(HeadHunterResponseCollectionError):
    """Access denied error from HeadHunter API."""


class ResponseCollectionHHApiProtocol(Protocol):
    def get_responses_from_collection(
        self, collection_id: str, vacancy_id: str, access_token: str
    ) -> AsyncGenerator[Item2]: ...

    async def get_resume(self, resume_id: str, access_token: str) -> ResumeResumeForEmployer: ...
