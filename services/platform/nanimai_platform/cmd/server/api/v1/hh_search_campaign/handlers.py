# mypy: disable-error-code="misc"
# ^^^ mypy не умеет работать с динамическими енамами
import contextlib
import functools
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

import grpclib.exceptions
import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import nanimai_platform.external_clients.hharon.hharon_api.v1 as hharon_api
from nanimai_platform.cmd.server.api.v1.hh_search_campaign.dto import (
    GetAccessResponseDTO,
    GetHHSuggestionRequestDTO,
    GetHHSuggestionResponseDTO,
    GetHHSuggestionsListResponseDTO,
    GetSearchCampaignPreviewRequestDTO,
    GetSearchCampaignPreviewResponseDTO,
    GetSearchCampaignSettingsResponseDTO,
    GetStatusResponseDTO,
    SaveHHSearchCampaignSettingsRequestDTO,
    SearchCampaignPayloadDTO,
    SearchCampaignSettingsDTO,
    StatusDTO,
)
from nanimai_platform.cmd.server.dependencies import authorized
from nanimai_platform.domain.scalar.scalars import VacancyID
from nanimai_platform.services import (
    HHSearchCampaignService,
    HHSearchCampaignServiceVacancyAccessDeniedError,
    HHSearchCampaignServiceVacancyNotFoundError,
)
from nanimai_platform.services.authorization.service import AuthorizationService
from nanimai_platform.services.hharon_proxy.service import (
    HHaronProxyService,
    HharonError,
    HharonInvalidArgumentError,
    HharonNotFoundError,
)
from nanimai_platform.utils.map_grpc_error import AdvancedGRPCError

router = APIRouter(tags=["hh_search_campaign"])

log = structlog.stdlib.get_logger("app.router.hh_search_campaign")


def catch_errors[**P, R](func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> R:  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
        try:
            return await func(*args, **kwargs)  # pyright: ignore[reportAny]
        except HTTPException:
            raise
        except HharonNotFoundError as e:
            log.error("not found error when getting suggestion", err=e)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ничего не найдено",
            ) from e
        except HharonInvalidArgumentError as e:
            log.error("invalid data in request (or in response)", err=e)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
            ) from e
        except HharonError as e:
            log.error("internal server error when getting suggestion", err=e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
            ) from e
        except grpclib.exceptions.GRPCError as e:
            adv = AdvancedGRPCError.from_grpc(e)
            log.error(adv.log, err=e)
            raise HTTPException(status_code=adv.http_code, detail=adv.detail) from e
        except Exception as e:
            log.error("failed to get suggestion", err=e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
            ) from e

    return wrapper  # pyright: ignore[reportUnknownVariableType]


@router.post("/preview")
@catch_errors
@inject
async def post_search_campaign_preview(
    *,
    request_body: GetSearchCampaignPreviewRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    auth_service: FromDishka[AuthorizationService],
    hharon_proxy: FromDishka[HHaronProxyService],
) -> GetSearchCampaignPreviewResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)

    campaign = request_body.payload.to_proto()
    campaign.user_id = str(user.id)
    campaign.daily_limit = request_body.settings.daily_limit
    campaign.active_until = datetime.now(UTC) + timedelta(days=request_body.settings.duration_days)

    response = await hharon_proxy.get_search_campaign_preview(user.id, campaign)

    return GetSearchCampaignPreviewResponseDTO(
        total_candidates=response.found_total_candidates,
        interval_seconds=response.interval_seconds,
        candidates_per_run=response.candidates_per_run,
    )


@router.get("/settings")
@catch_errors
@inject
async def get_search_campaign_settings(
    *,
    vacancy_id: VacancyID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    auth_service: FromDishka[AuthorizationService],
    hharon_proxy: FromDishka[HHaronProxyService],
) -> GetSearchCampaignSettingsResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)

    response = await hharon_proxy.get_search_campaign_settings(vacancy_id=vacancy_id)
    campaign = response.campaign
    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Кампания не найдена",
        ) from None

    active_until = campaign.active_until
    today = datetime.now(UTC).date()
    duration_days = max(
        0,
        (active_until.date() - today).days if active_until else 0,
    )

    return GetSearchCampaignSettingsResponseDTO(
        payload=SearchCampaignPayloadDTO.from_proto(campaign),
        settings=SearchCampaignSettingsDTO(
            daily_limit=campaign.daily_limit,
            duration_days=duration_days,
        ),
    )


@router.post("/settings")
@catch_errors
@inject
async def post_save_search_campaign_settings(
    *,
    request_body: SaveHHSearchCampaignSettingsRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    auth_service: FromDishka[AuthorizationService],
    hharon_proxy: FromDishka[HHaronProxyService],
) -> GetStatusResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)

    campaign = request_body.payload.to_proto()
    campaign.user_id = str(user.id)
    campaign.vacancy_id = str(request_body.vacancy_id)
    campaign.daily_limit = request_body.settings.daily_limit
    campaign.active_until = datetime.now(UTC) + timedelta(days=request_body.settings.duration_days)

    response = await hharon_proxy.create_search_campaign(campaign)
    _ = await hharon_proxy.init_search_campaign(
        hharon_api.InitSearchCampaignExecutionRequest(vacancy_id=response.vacancy_id)
    )

    return GetStatusResponseDTO(status="active", active_until=None, collected_current=None, collected_maximum=None)


@router.get("/hh_suggestion")
@catch_errors
@inject
async def get_hh_suggestion(
    *,
    query: Annotated[GetHHSuggestionRequestDTO, Query()],
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    auth_service: FromDishka[AuthorizationService],
    hharon_proxy: FromDishka[HHaronProxyService],
) -> GetHHSuggestionsListResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)

    response = await hharon_proxy.get_headhunter_suggestions(
        field=hharon_api.GetHeadhunterSuggestionsRequestField[query.field.name], text=query.text
    )

    return GetHHSuggestionsListResponseDTO(
        items=[GetHHSuggestionResponseDTO(id=item.hh_id, text=item.text) for item in response.suggestions],
    )


@router.get("/prefill_from_vacancy")
@catch_errors
@inject
async def get_prefill_from_vacancy(
    *,
    vacancy_id: VacancyID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    auth_service: FromDishka[AuthorizationService],
    hh_search_campaign_service: FromDishka[HHSearchCampaignService],
) -> SearchCampaignPayloadDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        payload = await hh_search_campaign_service.get_prefill_from_vacancy(
            hh_search_campaign_service.GetPrefillFromVacancyRequest(
                user_id=user.id,
                vacancy_id=vacancy_id,
            )
        )
        return SearchCampaignPayloadDTO.from_proto(payload)
    except HHSearchCampaignServiceVacancyNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вакансия не найдена",
        ) from None
    except HHSearchCampaignServiceVacancyAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к вакансии",
        ) from None


@router.get("/prefill_from_url")
@catch_errors
@inject
async def get_prefill_from_url(
    *,
    url: str,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    auth_service: FromDishka[AuthorizationService],
    hharon_proxy: FromDishka[HHaronProxyService],
) -> SearchCampaignPayloadDTO:
    _ = await authorized.get_current_user(credentials, auth_service)

    response = await hharon_proxy.extract_from_url(url)
    if response.campaign is None:
        return SearchCampaignPayloadDTO()

    return SearchCampaignPayloadDTO.from_proto(response.campaign)


@router.get("/status")
@catch_errors
@inject
async def get_status_handler(
    *,
    vacancy_id: VacancyID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    auth_service: FromDishka[AuthorizationService],
    hharon_proxy: FromDishka[HHaronProxyService],
) -> GetStatusResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)

    response = None
    with contextlib.suppress(Exception):
        response = await hharon_proxy.get_search_campaign_status(vacancy_id=vacancy_id)

    status_mapping: dict[hharon_api.SearchCampaignStatus, StatusDTO] = {
        hharon_api.SearchCampaignStatus.UNSPECIFIED: "not_exist",
        hharon_api.SearchCampaignStatus.CREATED: "not_exist",
        hharon_api.SearchCampaignStatus.ACTIVE: "active",
        hharon_api.SearchCampaignStatus.COMPLETED: "completed",
        hharon_api.SearchCampaignStatus.FAILED: "failed",
    }

    campaign_status: StatusDTO = status_mapping.get(response.status, "not_exist") if response else "not_exist"

    return GetStatusResponseDTO(
        status=campaign_status,
        active_until=response.active_until if response and campaign_status != "not_exist" else None,
        collected_current=response.collected_current if response and campaign_status != "not_exist" else None,
        collected_maximum=response.collected_maximum if response and campaign_status != "not_exist" else None,
    )


@router.post("/stop")
@catch_errors
@inject
async def post_stop_handler(
    *,
    vacancy_id: VacancyID,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    auth_service: FromDishka[AuthorizationService],
    hharon_proxy: FromDishka[HHaronProxyService],
) -> GetStatusResponseDTO:
    _ = await authorized.get_current_user(credentials, auth_service)
    _ = await hharon_proxy.complete_search_campaign_execution(vacancy_id=vacancy_id)

    return GetStatusResponseDTO(status="completed", active_until=None, collected_current=None, collected_maximum=None)


@router.get("/access")
@catch_errors
@inject
async def get_access_handler(
    *,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    auth_service: FromDishka[AuthorizationService],
    hharon_proxy: FromDishka[HHaronProxyService],
) -> GetAccessResponseDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    response = await hharon_proxy.get_headhunter_search_campaign_access(user_id=user.id)

    return GetAccessResponseDTO(
        has_access=response.access,
        account_name=response.hh_account_name if response.access else None,
        account_email=response.hh_account_email if response.access else None,
        expires_at=response.expires_at,
    )
