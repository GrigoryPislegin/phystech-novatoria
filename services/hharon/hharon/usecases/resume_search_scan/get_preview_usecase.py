import hashlib
from dataclasses import dataclass
from datetime import timedelta
from math import ceil
from typing import final

import structlog
from pydantic import BaseModel, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.infra.resume_search_scan import ResumeSearchScanConfig
from hharon.pkg import hhapi
from hharon.protocols import CacheProtocol
from hharon.protocols.resume_search_scan import protocol as resume_search_scan_protocol
from hharon.usecases.hh_search_campaign.mapper import SearchCampaignMapperUsecase
from hharon.usecases.token.get_tokens import GetTokens, GetTokensError
from hharon_api.v1 import hharon_pb2

log = structlog.stdlib.get_logger("hharon.usecases.GetSearchCampaignPreviewUsecase")

CACHE_KEY_PREFIX = "search_campaign_preview"
CACHE_TTL = timedelta(minutes=5)

_PARAMS_ADAPTER = TypeAdapter(list[hhapi.ResumesGetParameters])


class GetSearchCampaignPreviewError(Exception): ...


class GetSearchCampaignPreviewAccessDeniedError(GetSearchCampaignPreviewError): ...


class GetSearchCampaignPreviewRateLimitError(GetSearchCampaignPreviewError):
    retry_after: int | None

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@final
@dataclass(slots=True)
class GetSearchCampaignPreviewUsecase:
    _hh_client: resume_search_scan_protocol.ResumeSearchScanHHApiProtocol
    _get_tokens: GetTokens[AsyncSession]
    _cache: CacheProtocol
    _config: ResumeSearchScanConfig
    _mapper: SearchCampaignMapperUsecase

    @dataclass
    class GetPreviewRequest:
        campaign: hharon_pb2.SearchCampaign

    class GetPreviewResponse(BaseModel):
        total_candidates: int
        interval_seconds: int
        candidates_per_run: int

    async def get_preview(self, request: GetPreviewRequest) -> GetPreviewResponse:
        campaign_proto = request.campaign
        if campaign_proto is None:  # pyright: ignore[reportUnnecessaryComparison]
            raise GetSearchCampaignPreviewError("campaign is required")

        user_id = campaign_proto.user_id or ""
        if not user_id:
            raise GetSearchCampaignPreviewError("user_id is required in campaign")

        campaign = self._mapper.from_proto(campaign_proto)
        search_params = campaign.search_params

        hash_key = self._params_hash(search_params)
        cache_key = f"{CACHE_KEY_PREFIX}:{user_id}:{hash_key}"

        cached = await self._cache.get(cache_key, unmarshal_as=self.GetPreviewResponse)
        if cached is not None:
            log.debug("search_campaign_preview_cache_hit", user_id=user_id)
            return cached

        try:
            tokens = await self._get_tokens.get_tokens(GetTokens.GetTokensRequest(user_id=user_id))
        except GetTokensError as e:
            log.exception("failed to get tokens for user_id", user_id=user_id, err=e)
            raise GetSearchCampaignPreviewAccessDeniedError from e

        try:
            total_candidates = await self._hh_client.get_resume_search_count(tokens.access_token, search_params)
        except resume_search_scan_protocol.HeadHunterAccessDeniedError as e:
            log.warning("user has no access to resume search", user_id=user_id, err=e)
            raise GetSearchCampaignPreviewAccessDeniedError from e
        except resume_search_scan_protocol.HeadHunterRateLimitError as e:
            raise GetSearchCampaignPreviewRateLimitError(str(e), retry_after=e.retry_after) from e
        except resume_search_scan_protocol.HeadHunterResumeSearchScanError as e:
            log.exception("resume search error", user_id=user_id, err=e)
            raise GetSearchCampaignPreviewError from e

        interval_seconds = int(self._config.interval.total_seconds())
        candidates_per_run = ceil(campaign.daily_limit / self._config.scans_per_day)

        response = self.GetPreviewResponse(
            total_candidates=total_candidates,
            interval_seconds=interval_seconds,
            candidates_per_run=candidates_per_run,
        )

        await self._cache.set(cache_key, response, ttl=CACHE_TTL)

        return response

    def _params_hash(self, params: list[hhapi.ResumesGetParameters]) -> str:
        json_bytes = _PARAMS_ADAPTER.dump_json(
            params,
            by_alias=False,
            exclude_unset=True,
            exclude_defaults=True,
            exclude_none=True,
            exclude={"page", "per_page"},
        )
        return hashlib.sha256(json_bytes).hexdigest()
