from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

from hharon.domain.known_candidate import KnownCandidateSourceEnum
from hharon.domain.response_collection import ProcessedCandidate, ResponseCollectionSettings, ResponseCollectionStatus
from hharon.domain.scalars import ResponseCollectionSettingsID


class ResponseCollectionRepositoryProtocol[SessionT](Protocol):
    @asynccontextmanager
    async def context(self) -> AsyncGenerator[SessionT]:
        raise NotImplementedError("ResponseCollectionRepositoryProtocol.context")
        yield  # pyright: ignore[reportUnreachable]

    @dataclass
    class CreateSettingsRequest:
        user_id: str
        vacancy_id: str
        hh_vacancy_id: str
        hh_collections: list[str]

    async def create_settings(
        self, session: SessionT, request: CreateSettingsRequest
    ) -> ResponseCollectionSettings: ...

    @dataclass
    class GetSettingsRequest:
        settings_id: ResponseCollectionSettingsID

    async def get_settings(
        self, session: SessionT, request: GetSettingsRequest
    ) -> ResponseCollectionSettings | None: ...

    @dataclass
    class GetSettingsByVacancyRequest:
        vacancy_id: str

    async def get_settings_by_vacancy(
        self, session: SessionT, request: GetSettingsByVacancyRequest
    ) -> ResponseCollectionSettings | None: ...

    @dataclass
    class MarkCandidateProcessedRequest:
        resume_id: str
        vacancy_id: str
        source: KnownCandidateSourceEnum
        source_id: ResponseCollectionSettingsID

    async def mark_candidate_processed(
        self, session: SessionT, request: MarkCandidateProcessedRequest
    ) -> ProcessedCandidate | None: ...

    @dataclass
    class IsCandidateProcessedRequest:
        resume_id: str
        settings_id: ResponseCollectionSettingsID

    async def is_candidate_processed(self, session: SessionT, request: IsCandidateProcessedRequest) -> bool: ...

    @dataclass
    class UpdateSettingsStatusRequest:
        settings_id: ResponseCollectionSettingsID
        status: ResponseCollectionStatus

    async def update_settings_status(self, session: SessionT, request: UpdateSettingsStatusRequest) -> None: ...
