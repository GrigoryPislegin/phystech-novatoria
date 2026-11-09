from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import final

import pydantic
import structlog
from google.protobuf.timestamp_pb2 import Timestamp

from hharon.domain.scalars import SearchCampaignID
from hharon.domain.search_campaign import SearchCampaignStatus
from hharon.protocols import resume_search_scan as resume_search_scan_protocol
from hharon.usecases.hh_search_campaign.mapper import SearchCampaignMapperUsecase
from hharon.usecases.token.get_tokens import GetTokens
from hharon_api.v1 import hharon_pb2

log = structlog.stdlib.get_logger("hharon.usecases.SearchCampaignUsecaseError")


class SearchCampaignUsecaseError(Exception): ...


class SearchCampaignUsecaseTokenError(SearchCampaignUsecaseError): ...


class SearchCampaignUsecaseHHAPIError(SearchCampaignUsecaseError): ...


class SearchCampaignUsecaseNotFoundError(SearchCampaignUsecaseError): ...


class SearchCampaignUsecaseActiveCampaignExistsError(SearchCampaignUsecaseError):
    """Raised when creating a campaign but an active campaign already exists for the vacancy."""


@final
class SearchCampaignUsecase[SessionT]:
    def __init__(
        self,
        *,
        resume_search_scan_repository: resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol[SessionT],
        get_tokens_usecase: GetTokens[SessionT],
        mapper: SearchCampaignMapperUsecase,
    ) -> None:
        self._resume_search_scan_repository = resume_search_scan_repository
        self._get_tokens_usecase = get_tokens_usecase
        self._mapper = mapper

    @dataclass
    class CreateSearchCampaignResponse:
        vacancy_id: str

    async def create(self, request: hharon_pb2.SearchCampaign) -> CreateSearchCampaignResponse:
        """Create saved search filter on HeadHunter and save to database"""
        try:
            campaign = self._mapper.from_proto(request)

            async with self._resume_search_scan_repository.context() as session:
                existing_campaign = await self._resume_search_scan_repository.get_campaign_by_vacancy(
                    session,
                    self._resume_search_scan_repository.GetCampaignByVacancyRequest(vacancy_id=campaign.vacancy_id),
                )
                if existing_campaign is not None and existing_campaign.status == SearchCampaignStatus.ACTIVE:
                    msg = f"Active campaign already exists for vacancy_id={campaign.vacancy_id}"
                    raise SearchCampaignUsecaseActiveCampaignExistsError(msg)

                db_search_campaign = await self._resume_search_scan_repository.create_campaign(
                    session,
                    self._resume_search_scan_repository.CreateCampaignRequest(
                        user_id=campaign.user_id,
                        vacancy_id=campaign.vacancy_id,
                        status=campaign.status,
                        active_until=campaign.active_until,
                        daily_limit=campaign.daily_limit,
                        search_params=campaign.search_params,
                    ),
                )

            return self.CreateSearchCampaignResponse(vacancy_id=db_search_campaign.vacancy_id)

        except SearchCampaignUsecaseActiveCampaignExistsError:
            raise
        except Exception as e:
            log.exception("unexpected error in create search campaign", error=str(e))
            raise SearchCampaignUsecaseError("unexpected error") from e

    class GetSearchCampaignStatusRequest(pydantic.BaseModel):
        vacancy_id: str

    class GetSearchCampaignStatusResponse(pydantic.BaseModel):
        search_campaign_id: SearchCampaignID
        status: SearchCampaignStatus
        user_id: str
        vacancy_id: str
        active_until: datetime
        collected_current: int
        daily_maximum: int

    async def get_search_campaign_status(
        self, request: GetSearchCampaignStatusRequest
    ) -> GetSearchCampaignStatusResponse:
        """Get search campaign status by vacancy_id"""
        try:
            async with self._resume_search_scan_repository.context() as session:
                search_campaign = await self._resume_search_scan_repository.get_campaign_by_vacancy(
                    session,
                    self._resume_search_scan_repository.GetCampaignByVacancyRequest(vacancy_id=request.vacancy_id),
                )

            if search_campaign is None:
                error_msg = f"Search campaign not found for vacancy_id={request.vacancy_id}"
                raise SearchCampaignUsecaseNotFoundError(error_msg)

            async with self._resume_search_scan_repository.context() as session:
                collected_current = await self._resume_search_scan_repository.count_collected_by_date(
                    session,
                    self._resume_search_scan_repository.CountCollectedTodayRequest(
                        campaign_id=SearchCampaignID.from_uuid(search_campaign.id),
                        date=datetime.now(UTC).date(),
                    ),
                )

            return self.GetSearchCampaignStatusResponse(
                search_campaign_id=SearchCampaignID.from_uuid(search_campaign.id),
                status=search_campaign.status,
                user_id=search_campaign.user_id,
                vacancy_id=search_campaign.vacancy_id,
                collected_current=collected_current.collected_current,
                daily_maximum=search_campaign.daily_limit,
                active_until=search_campaign.active_until,
            )
        except SearchCampaignUsecaseNotFoundError:
            raise
        except Exception as e:
            log.exception("unexpected error in get search campaign status", error=str(e))
            raise SearchCampaignUsecaseError("unexpected error") from e

    class GetSearchCampaignSettingsRequest(pydantic.BaseModel):
        vacancy_id: str

    async def get_search_campaign_settings(
        self, request: GetSearchCampaignSettingsRequest
    ) -> hharon_pb2.SearchCampaign:
        try:
            async with self._resume_search_scan_repository.context() as session:
                search_campaign = await self._resume_search_scan_repository.get_campaign_by_vacancy(
                    session,
                    self._resume_search_scan_repository.GetCampaignByVacancyRequest(vacancy_id=request.vacancy_id),
                )

            if search_campaign is None:
                error_msg = f"Search campaign not found for vacancy_id={request.vacancy_id}"
                raise SearchCampaignUsecaseNotFoundError(error_msg)

            campaign_proto = self._mapper.from_params(search_campaign.search_params)
            campaign_proto.user_id = search_campaign.user_id
            campaign_proto.vacancy_id = search_campaign.vacancy_id
            campaign_proto.daily_limit = search_campaign.daily_limit
            active_until_ts = Timestamp()
            active_until_ts.FromDatetime(search_campaign.active_until)
            campaign_proto.active_until.CopyFrom(active_until_ts)

        except SearchCampaignUsecaseNotFoundError:
            raise
        except Exception as e:
            log.exception("unexpected error in get search campaign settings", error=str(e))
            raise SearchCampaignUsecaseError("unexpected error") from e
        else:
            return campaign_proto
