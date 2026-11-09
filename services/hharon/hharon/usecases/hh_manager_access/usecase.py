from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import final

import pydantic
import structlog

from hharon.pkg import hhapi
from hharon.protocols import CacheProtocol, ResumeSearchScanHHApiProtocol
from hharon.usecases.token.get_tokens import GetTokens, GetTokensError
from hharon.usecases.user.get_user import GetHharonUser, GetHharonUserError

log = structlog.stdlib.get_logger("hharon.usecases.GetManagerAccessUsecase")


class GetManagerAccessUsecaseError(Exception): ...


class GetManagerAccessUsecaseTokenError(GetManagerAccessUsecaseError): ...


class GetManagerAccessUsecaseUserError(GetManagerAccessUsecaseError): ...


class GetManagerAccessUsecaseHHAPIError(GetManagerAccessUsecaseError): ...


@final
@dataclass(slots=True)
class GetHHSearchCampaignAccessUsecase[SessionT]:
    _get_tokens_usecase: GetTokens[SessionT]
    _hh_api: ResumeSearchScanHHApiProtocol
    _get_user_usecase: GetHharonUser[SessionT]
    _cache: CacheProtocol

    @dataclass
    class GetHHSearchCampaignAccessRequest:
        user_id: str

    class GetHHSearchCampaignAccessResponse(pydantic.BaseModel):
        access: bool
        expires_at: datetime | None
        hh_account_name: str
        hh_account_email: str

    async def get_headhunter_search_campaign_access(
        self, request: GetHHSearchCampaignAccessRequest
    ) -> GetHHSearchCampaignAccessResponse:
        try:
            if cache := await self._cache.get(
                self._cache_key(request.user_id), unmarshal_as=self.GetHHSearchCampaignAccessResponse
            ):
                return cache

            tokens, user_response = await asyncio.gather(
                self._get_tokens_usecase.get_tokens(GetTokens.GetTokensRequest(user_id=request.user_id)),
                self._get_user_usecase.get_user(GetHharonUser.GetHharonUserRequest(user_id=request.user_id)),
            )

            has_access = False
            with contextlib.suppress(Exception):
                # try making request to hh api
                _ = self._hh_api.get_resumes_from_search(
                    tokens.access_token, [hhapi.ResumesGetParameters(text="Резюме")]
                )
                has_access = True

            response = self.GetHHSearchCampaignAccessResponse(
                access=has_access,
                expires_at=None,  # no info
                hh_account_name=user_response.user.name,
                hh_account_email=user_response.user.email,
            )

            await self._cache.set(self._cache_key(request.user_id), response, ttl=timedelta(minutes=10))
            return response  # noqa: TRY300
        except GetTokensError as exc:
            log.exception("failed to get tokens", error=str(exc))
            raise GetManagerAccessUsecaseTokenError("failed to get manager access due to get tokens") from exc
        except GetHharonUserError as exc:
            log.exception("failed to get user", error=str(exc))
            raise GetManagerAccessUsecaseUserError("failed to get manager access due to get user") from exc
        except Exception as e:
            log.exception("unexpected error in get manager access", error=str(e))
            raise GetManagerAccessUsecaseError("unexpected error") from e

    def _cache_key(self, user_id: str) -> str:
        return f"search_campaign_access:{user_id}"
