from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from hharon.domain.known_candidate import KnownCandidateSourceEnum
from hharon.domain.resume_search_scan import ProcessedScanCandidate
from hharon.domain.scalars import SearchCampaignID
from hharon.domain.search_campaign import SearchCampaign, SearchCampaignStatus
from hharon.pkg import hhapi
from hharon.pkg.hhapi.models import ResumeResumeForEmployer, ResumesSearchForResumesItem


class ResumeSearchScanRepositoryProtocol[SessionT](Protocol):
    @asynccontextmanager
    async def context(self) -> AsyncGenerator[SessionT]:
        raise NotImplementedError("ResumeSearchScanRepositoryProtocol.context")
        yield  # pyright: ignore[reportUnreachable]

    @dataclass
    class CreateCampaignRequest:
        user_id: str
        vacancy_id: str
        status: SearchCampaignStatus

        active_until: datetime
        daily_limit: int

        search_params: list[hhapi.ResumesGetParameters]

    async def create_campaign(self, session: SessionT, request: CreateCampaignRequest) -> SearchCampaign: ...

    @dataclass
    class UpdateCampaignStatusRequest:
        campaign_id: SearchCampaignID
        status: SearchCampaignStatus

    async def update_campaign_status(self, session: SessionT, request: UpdateCampaignStatusRequest) -> None: ...

    @dataclass
    class GetCampaignRequest:
        campaign_id: SearchCampaignID

    async def get_campaign(self, session: SessionT, request: GetCampaignRequest) -> SearchCampaign | None: ...

    @dataclass
    class GetCampaignByVacancyRequest:
        vacancy_id: str

    async def get_campaign_by_vacancy(
        self, session: SessionT, request: GetCampaignByVacancyRequest
    ) -> SearchCampaign | None: ...

    @dataclass
    class DeleteCampaignRequest:
        campaign_id: SearchCampaignID

    async def delete_campaign(self, session: SessionT, request: DeleteCampaignRequest) -> None: ...

    @dataclass
    class MarkCandidateProcessedRequest:
        resume_id: str
        vacancy_id: str
        source: KnownCandidateSourceEnum
        source_id: SearchCampaignID

    async def mark_candidate_processed(
        self, session: SessionT | None, request: MarkCandidateProcessedRequest
    ) -> ProcessedScanCandidate | None: ...

    @dataclass
    class CountCollectedTodayRequest:
        campaign_id: SearchCampaignID
        date: date

    @dataclass
    class CountCollectedTodayResponse:
        collected_current: int

    async def count_collected_by_date(
        self, session: SessionT, request: CountCollectedTodayRequest
    ) -> CountCollectedTodayResponse: ...


class HeadHunterResumeSearchScanError(Exception):
    """Base exception for HeadHunter resume search scan errors."""


class HeadHunterRateLimitError(HeadHunterResumeSearchScanError):
    """Rate limit error from HeadHunter API."""

    retry_after: int | None

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class HeadHunterAccessDeniedError(HeadHunterResumeSearchScanError):
    """Access denied error from HeadHunter API."""


class ResumeSearchScanHHApiProtocol(Protocol):
    """Protocol for HH API: get resumes from saved search (filter)."""

    def get_resumes_from_search(
        self, access_token: str, params: list[hhapi.ResumesGetParameters]
    ) -> AsyncGenerator[ResumesSearchForResumesItem]: ...

    async def get_resume_search_count(self, access_token: str, params: list[hhapi.ResumesGetParameters]) -> int: ...

    async def get_resume(self, resume_id: str, access_token: str) -> ResumeResumeForEmployer: ...
