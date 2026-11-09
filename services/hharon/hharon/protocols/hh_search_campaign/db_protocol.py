from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

from hharon.domain.scalars import SearchCampaignID
from hharon.domain.search_campaign import SearchCampaign
from hharon.pkg import hhapi


class SearchCampaignRepositoryProtocol[SessionT](Protocol):
    @asynccontextmanager
    async def context(self) -> AsyncGenerator[SessionT]:
        raise NotImplementedError("SearchCampaignRepositoryProtocol.context")
        yield  # pyright: ignore[reportUnreachable]

    @dataclass
    class CreateSearchCampaignRequest:
        user_id: str
        vacancy_id: str
        hh_vacancy_id: str | None
        params: list[hhapi.ResumesGetParameters]

    async def create_search_campaign(
        self, session: SessionT, request: CreateSearchCampaignRequest
    ) -> SearchCampaign: ...

    @dataclass
    class ReadLastSearchCampaignRequest:
        vacancy_id: str
        user_id: str

    async def read_last_search_campaign(
        self, session: SessionT, request: ReadLastSearchCampaignRequest
    ) -> SearchCampaign | None: ...

    @dataclass
    class DeleteSearchCampaignRequest:
        id: SearchCampaignID

    async def delete_search_campaign(self, session: SessionT, request: DeleteSearchCampaignRequest) -> None: ...
