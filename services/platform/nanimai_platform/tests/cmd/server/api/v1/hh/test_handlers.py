from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, create_autospec, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials

from nanimai_platform.cmd.server.api.v1.hh_oauth2 import dto, handlers
from nanimai_platform.domain import Tariff, Tutorials, UserID, UserProfile
from nanimai_platform.protocols.external.oauth2 import OAuth2Protocol
from nanimai_platform.services.oauth2 import OAuth2Service, OAuth2ServiceAPIError, OAuth2ServiceUserNotFoundError


@pytest.mark.asyncio
async def test_api_init_oauth_flow_hh_oauth2_returns_link(dishka_request_factory) -> None:
    user = UserProfile(
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

    oauth2_service = create_autospec(OAuth2Service, instance=True, spec_set=True)
    oauth2_service.generate_hh_link = AsyncMock(
        return_value=OAuth2Protocol.GenerateOAuthLinkResponse(redirect_back="https://hh.ru/oauth/authorize?state=STATE")
    )

    with patch.object(handlers.authorized, "get_current_user", AsyncMock(return_value=user)):
        async with dishka_request_factory(native_oauth2_service=oauth2_service) as req:
            hh_oauth2_init = cast(Any, handlers.hh_oauth2_init)
            resp = await hh_oauth2_init(
                query=dto.InitOAuth2FlowRequestDTO(redirect_back="https://example.com/after"),
                credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="TOKEN"),
                ___dishka_request=req,
            )
        assert resp.redirect_url == "https://hh.ru/oauth/authorize?state=STATE"
        oauth2_service.generate_hh_link.assert_awaited()


@pytest.mark.asyncio
async def test_api_init_oauth_flow_maps_user_not_found(dishka_request_factory) -> None:
    user = UserProfile(
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
    oauth2_service = create_autospec(OAuth2Service, instance=True, spec_set=True)
    oauth2_service.generate_hh_link = AsyncMock(side_effect=OAuth2ServiceUserNotFoundError("x"))

    with patch.object(handlers.authorized, "get_current_user", AsyncMock(return_value=user)):
        with pytest.raises(HTTPException) as e:
            async with dishka_request_factory(native_oauth2_service=oauth2_service) as req:
                hh_oauth2_init = cast(Any, handlers.hh_oauth2_init)
                await hh_oauth2_init(
                    query=dto.InitOAuth2FlowRequestDTO(redirect_back="https://example.com/after"),
                    credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="TOKEN"),
                    ___dishka_request=req,
                )
        assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_api_init_oauth_flow_maps_api_error(dishka_request_factory) -> None:
    user = UserProfile(
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
    oauth2_service = create_autospec(OAuth2Service, instance=True, spec_set=True)
    oauth2_service.generate_hh_link = AsyncMock(side_effect=OAuth2ServiceAPIError("x"))

    with patch.object(handlers.authorized, "get_current_user", AsyncMock(return_value=user)):
        with pytest.raises(HTTPException) as e:
            async with dishka_request_factory(native_oauth2_service=oauth2_service) as req:
                hh_oauth2_init = cast(Any, handlers.hh_oauth2_init)
                await hh_oauth2_init(
                    query=dto.InitOAuth2FlowRequestDTO(redirect_back="https://example.com/after"),
                    credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="TOKEN"),
                    ___dishka_request=req,
                )
        assert e.value.status_code == 502


@pytest.mark.asyncio
async def test_api_complete_oauth_flow_redirects_back(dishka_request_factory) -> None:
    oauth2_service = create_autospec(OAuth2Service, instance=True, spec_set=True)
    oauth2_service.store_secret_code = AsyncMock(
        return_value=OAuth2Service.StoreSecretCodeResponse(redirect_back="https://example.com/after")
    )

    async with dishka_request_factory(native_oauth2_service=oauth2_service) as req:
        hh_oauth2_complete = cast(Any, handlers.hh_oauth2_complete)
        resp = await hh_oauth2_complete(
            query=dto.CompleteOAuth2FlowRequestDTO(code="CODE", state="STATE"),
            ___dishka_request=req,
        )
    assert isinstance(resp, RedirectResponse)
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://example.com/after"


@pytest.mark.asyncio
async def test_api_complete_oauth_flow_rejects_if_user_cancelled(dishka_request_factory) -> None:
    oauth2_service = create_autospec(OAuth2Service, instance=True, spec_set=True)
    oauth2_service.store_secret_code = AsyncMock()

    with pytest.raises(HTTPException) as e:
        async with dishka_request_factory(native_oauth2_service=oauth2_service) as req:
            hh_oauth2_complete = cast(Any, handlers.hh_oauth2_complete)
            await hh_oauth2_complete(
                query=dto.CompleteOAuth2FlowRequestDTO(code=None, error="access_denied", state="STATE"),
                ___dishka_request=req,
            )
    assert e.value.status_code == 500
