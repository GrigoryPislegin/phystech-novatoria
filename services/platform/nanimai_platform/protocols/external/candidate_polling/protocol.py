from abc import ABC, abstractmethod
from enum import StrEnum

from pydantic import BaseModel

from nanimai_platform.utils import NTDict


class MoveToCollectionEnum(StrEnum):
    CONSIDER = "consider"


class CandidatePollingProtocol(ABC):
    class RetrieveUnprocessedCandidatesRequest(BaseModel):
        ext_api_vacancy_id: str
        access_token: str

    @abstractmethod
    async def retrieve_unprocessed_candidates(
        self, request: RetrieveUnprocessedCandidatesRequest
    ) -> list[NTDict] | None:
        """
        Retrieves unprocessed candidates by vacancy_id from the API

        Returns:
            list[NTDict] | None - list of unprocessed candidates or None if failed with error
        """
        ...

    class RetrieveCollectionsPerVacancyRequest(BaseModel):
        ext_api_vacancy_id: str
        access_token: str

    @abstractmethod
    async def retrieve_collections_per_vacancy(self, request: RetrieveCollectionsPerVacancyRequest) -> NTDict | None:
        """
        Retrieves collections by vacancy_id from the API

        Returns:
            NTDict | None - collections or None if failed with error
        """
        ...

    class RetrieveFullResumeRequest(BaseModel):
        resume_id: str
        access_token: str

    @abstractmethod
    async def retrieve_full_resume(self, request: RetrieveFullResumeRequest) -> NTDict | None:
        """
        Retrieves full resume of the candidate from the API

        Returns:
            NTDict | None - full resume or None if failed with error
        """
        ...

    @abstractmethod
    async def move_candidate_to_collection(
        self, item: NTDict, move_to: MoveToCollectionEnum, access_token: str
    ) -> None:
        """Moves candidate to collection by url found in item.actions"""
        ...
