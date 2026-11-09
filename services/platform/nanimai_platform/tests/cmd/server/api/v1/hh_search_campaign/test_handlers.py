from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, create_autospec, patch

import grpclib.exceptions
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from grpclib.const import Status as GRPCStatus

import nanimai_platform.external_clients.hharon.hharon_api.v1 as hharon_api
from nanimai_platform.cmd.server.api.v1.hh_search_campaign import dto, handlers
from nanimai_platform.domain import Tariff, Tutorials, UserID, UserProfile
from nanimai_platform.services.hharon_proxy.service import (
    HHaronProxyService,
    HharonError,
    HharonInvalidArgumentError,
    HharonNotFoundError,
)


def _make_user() -> UserProfile:
    return UserProfile(
        id=UserID("507f1f77bcf86cd799439011"),
        email="u@example.com",
        name="U",
        password="x",
        thumbnail_url="https://example.com/t.png",
        tariff=Tariff(title="Free", analysis_total=1, analysis_used=0),
        tutorials=Tutorials(platform=False, interview=False),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        deleted_at=None,
    )


def _make_preview_request() -> dto.GetSearchCampaignPreviewRequestDTO:
    return dto.GetSearchCampaignPreviewRequestDTO(
        payload=dto.SearchCampaignPayloadDTO(),
        settings=dto.SearchCampaignSettingsDTO(daily_limit=30, duration_days=7),
    )


@pytest.mark.asyncio
async def test_post_search_campaign_preview_returns_response_successfully(
    dishka_request_factory, make_oauth2_service
) -> None:
    """Test that post_search_campaign_preview returns response successfully."""
    oauth2_env = make_oauth2_service()
    hharon_proxy = create_autospec(HHaronProxyService, instance=True, spec_set=True)
    hharon_proxy.get_search_campaign_preview = AsyncMock(
        return_value=hharon_api.GetSearchCampaignPreviewResponse(
            found_total_candidates=150,
            interval_seconds=28800,
            candidates_per_run=10,
        )
    )

    with patch.object(handlers.authorized, "get_current_user", AsyncMock(return_value=_make_user())):
        async with dishka_request_factory(native_oauth2_service=oauth2_env.svc, hharon_proxy=hharon_proxy) as req:
            post_preview = cast(Any, handlers.post_search_campaign_preview)
            resp = await post_preview(
                request_body=_make_preview_request(),
                credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="TOKEN"),
                ___dishka_request=req,
            )
    assert resp.total_candidates == 150
    assert resp.interval_seconds == 28800
    assert resp.candidates_per_run == 10
    hharon_proxy.get_search_campaign_preview.assert_awaited_once()


@pytest.mark.asyncio
async def test_post_search_campaign_preview_raises_404_on_not_found(
    dishka_request_factory, make_oauth2_service
) -> None:
    """Test that post_search_campaign_preview raises 404 on HharonNotFoundError."""
    oauth2_env = make_oauth2_service()
    hharon_proxy = create_autospec(HHaronProxyService, instance=True, spec_set=True)
    hharon_proxy.get_search_campaign_preview = AsyncMock(side_effect=HharonNotFoundError("not found"))

    with patch.object(handlers.authorized, "get_current_user", AsyncMock(return_value=_make_user())):
        with pytest.raises(HTTPException) as exc_info:
            async with dishka_request_factory(native_oauth2_service=oauth2_env.svc, hharon_proxy=hharon_proxy) as req:
                post_preview = cast(Any, handlers.post_search_campaign_preview)
                await post_preview(
                    request_body=_make_preview_request(),
                    credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="TOKEN"),
                    ___dishka_request=req,
                )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_post_search_campaign_preview_raises_422_on_invalid_argument(
    dishka_request_factory, make_oauth2_service
) -> None:
    """Test that post_search_campaign_preview raises 422 on HharonInvalidArgumentError."""
    oauth2_env = make_oauth2_service()
    hharon_proxy = create_autospec(HHaronProxyService, instance=True, spec_set=True)
    hharon_proxy.get_search_campaign_preview = AsyncMock(side_effect=HharonInvalidArgumentError("invalid data"))

    with patch.object(handlers.authorized, "get_current_user", AsyncMock(return_value=_make_user())):
        with pytest.raises(HTTPException) as exc_info:
            async with dishka_request_factory(native_oauth2_service=oauth2_env.svc, hharon_proxy=hharon_proxy) as req:
                post_preview = cast(Any, handlers.post_search_campaign_preview)
                await post_preview(
                    request_body=_make_preview_request(),
                    credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="TOKEN"),
                    ___dishka_request=req,
                )
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_post_search_campaign_preview_raises_500_on_internal_error(
    dishka_request_factory, make_oauth2_service
) -> None:
    """Test that post_search_campaign_preview raises 500 on HharonError."""
    oauth2_env = make_oauth2_service()
    hharon_proxy = create_autospec(HHaronProxyService, instance=True, spec_set=True)
    hharon_proxy.get_search_campaign_preview = AsyncMock(side_effect=HharonError("internal error"))

    with patch.object(handlers.authorized, "get_current_user", AsyncMock(return_value=_make_user())):
        with pytest.raises(HTTPException) as exc_info:
            async with dishka_request_factory(native_oauth2_service=oauth2_env.svc, hharon_proxy=hharon_proxy) as req:
                post_preview = cast(Any, handlers.post_search_campaign_preview)
                await post_preview(
                    request_body=_make_preview_request(),
                    credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="TOKEN"),
                    ___dishka_request=req,
                )
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_post_search_campaign_preview_raises_429_on_rate_limit(
    dishka_request_factory, make_oauth2_service
) -> None:
    """Test that post_search_campaign_preview raises 429 on GRPC RESOURCE_EXHAUSTED (rate limit)."""
    oauth2_env = make_oauth2_service()
    hharon_proxy = create_autospec(HHaronProxyService, instance=True, spec_set=True)
    hharon_proxy.get_search_campaign_preview = AsyncMock(
        side_effect=grpclib.exceptions.GRPCError(GRPCStatus.RESOURCE_EXHAUSTED, "rate limit exceeded")
    )

    with patch.object(handlers.authorized, "get_current_user", AsyncMock(return_value=_make_user())):
        with pytest.raises(HTTPException) as exc_info:
            async with dishka_request_factory(native_oauth2_service=oauth2_env.svc, hharon_proxy=hharon_proxy) as req:
                post_preview = cast(Any, handlers.post_search_campaign_preview)
                await post_preview(
                    request_body=_make_preview_request(),
                    credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="TOKEN"),
                    ___dishka_request=req,
                )
    assert exc_info.value.status_code == 429
