from typing import Any, final
from unittest.mock import patch
from urllib import parse

import dishka
import pytest

from hharon.adapters.oauth2.hh import adapter as hh_adapter
from hharon.infra import HeadHunterClient, provide_headhunter_httpx_client
from hharon.infra.headhunter import HHClientConfig
from hharon.infra.oauth2 import HHOAuth2Config
from hharon.pkg import hhapi
from hharon.protocols import oauth2 as oauth2_protocol


@pytest.fixture
async def provider() -> dishka.Provider:
    @final
    class TempProvider(dishka.Provider):
        scope = dishka.Scope.APP

        @dishka.provide
        def hh_client_config(self) -> HHClientConfig:
            return HHClientConfig(
                user_agent="test-agent",
                timeout=30.0,
                base_url="https://test.headhunter.ru",
            )

        @dishka.provide
        def hh_oauth2_config(self) -> HHOAuth2Config:
            return HHOAuth2Config(
                client_id="client",
                client_secret="secret",
            )

        httpx_client = dishka.provide(staticmethod(provide_headhunter_httpx_client))
        hh_client = dishka.provide(HeadHunterClient)
        hh_oauth = dishka.provide(hh_adapter.HHOAuth2Adapter)

    return TempProvider()


@pytest.fixture
async def container(provider: dishka.Provider) -> dishka.AsyncContainer:
    return dishka.make_async_container(provider)


@pytest.fixture
async def hh_oauth2_adapter(container: dishka.AsyncContainer):
    """Fixture to create HHOAuth2Adapter for testing."""
    return await container.get(hh_adapter.HHOAuth2Adapter)


def test_hh_oauth2_adapter_generate_oauth_link_returns_redirect_url_from_request(
    hh_oauth2_adapter: hh_adapter.HHOAuth2Adapter,
) -> None:
    """Test that generate_oauth_link generates HeadHunter authorization URL with embedded redirect_url."""

    platform_redirect_url = "https://nanimai.tech/complete"
    state = "STATE"
    resp = hh_oauth2_adapter.generate_oauth_link(
        oauth2_protocol.OAuth2Protocol.GenerateOAuthLinkRequest(state=state, redirect_url=platform_redirect_url)
    )
    assert resp.redirect_url.startswith("https://hh.ru/oauth/authorize?")

    parsed_url = parse.urlparse(resp.redirect_url)
    params = parse.parse_qs(parsed_url.query)
    assert params["response_type"] == ["code"]
    assert params["client_id"] == ["client"]
    assert params["state"] == [state]
    assert params["redirect_uri"] == [platform_redirect_url]


@pytest.mark.asyncio
async def test_hh_oauth2_adapter_get_token_by_secret_code_parses_response(
    hh_oauth2_adapter: hh_adapter.HHOAuth2Adapter,
) -> None:
    """Test that get_token_by_secret_code correctly parses HeadHunter response."""

    async def _http_call(
        *_: Any,  # pyright: ignore[reportExplicitAny]
        response_model: type[hhapi.models.AuthUserToken],
        **__: Any,  # pyright: ignore[reportExplicitAny, reportAny, reportUnusedParameter]
    ) -> hhapi.models.AuthUserToken:
        assert response_model is hhapi.models.AuthUserToken

        return response_model(
            access_token="a",
            refresh_token="r",
            token_type="bearer",
            expires_in=10,
        )

    with patch.object(hh_oauth2_adapter._client, "post", _http_call):  # pyright: ignore[reportPrivateUsage]
        resp = await hh_oauth2_adapter.get_token_by_secret_code(
            oauth2_protocol.OAuth2Protocol.GetTokensBySecretCodeRequest(
                secret_code="CODE", redirect_uri="http://localhost:9704/complete"
            )
        )
    assert resp.token.access_token == "a"
    assert resp.token.refresh_token == "r"
    assert resp.token.token_type == "bearer"
    assert resp.token.expires_in == 10


@pytest.mark.asyncio
async def test_hh_oauth2_adapter_get_token_by_secret_code_validates_types(
    hh_oauth2_adapter: hh_adapter.HHOAuth2Adapter,
) -> None:
    """Test that get_token_by_secret_code validates response types."""

    async def _http_call(
        *_: Any,  # pyright: ignore[reportExplicitAny]
        response_model: type[hhapi.models.AuthUserToken],
        **__: Any,  # pyright: ignore[reportExplicitAny, reportAny, reportUnusedParameter]
    ) -> hhapi.models.AuthUserToken:
        assert response_model is hhapi.models.AuthUserToken
        raise oauth2_protocol.OAuth2ValidateError("invalid token response")

    with patch.object(hh_oauth2_adapter._client, "post", _http_call):  # pyright: ignore[reportPrivateUsage]
        with pytest.raises(oauth2_protocol.OAuth2ValidateError):
            _ = await hh_oauth2_adapter.get_token_by_secret_code(
                oauth2_protocol.OAuth2Protocol.GetTokensBySecretCodeRequest(
                    secret_code="CODE", redirect_uri="http://localhost:9704/complete"
                )
            )


@pytest.mark.asyncio
async def test_hh_oauth2_adapter_refresh_tokens_parses_response(
    hh_oauth2_adapter: hh_adapter.HHOAuth2Adapter,
) -> None:
    """Test that refresh_tokens correctly parses HeadHunter response."""

    async def _http_call(
        *_: Any,  # pyright: ignore[reportExplicitAny]
        response_model: type[hhapi.models.AuthUserToken],
        **__: Any,  # pyright: ignore[reportExplicitAny, reportAny, reportUnusedParameter]
    ) -> hhapi.models.AuthUserToken:
        assert response_model is hhapi.models.AuthUserToken

        return response_model(
            access_token="a2",
            refresh_token="r2",
            token_type="bearer",
            expires_in=11,
        )

    with patch.object(hh_oauth2_adapter._client, "post", _http_call):  # pyright: ignore[reportPrivateUsage]
        resp = await hh_oauth2_adapter.refresh_tokens(
            oauth2_protocol.OAuth2Protocol.RefreshTokensRequest(refresh_token="RR")
        )
    assert resp.token.access_token == "a2"
    assert resp.token.refresh_token == "r2"
    assert resp.token.expires_in == 11


@pytest.mark.asyncio
async def test_hh_oauth2_adapter_get_current_user_info_parses_response(
    hh_oauth2_adapter: hh_adapter.HHOAuth2Adapter,
) -> None:
    """Test that get_current_user_info correctly parses HeadHunter response."""

    async def _http_call(
        *_: Any,  # pyright: ignore[reportExplicitAny]
        response_model: type[hhapi.models.MeManagerProfile],
        **__: Any,  # pyright: ignore[reportExplicitAny, reportAny, reportUnusedParameter]
    ) -> hhapi.models.MeManagerProfile:
        assert response_model is hhapi.models.MeManagerProfile
        return response_model(
            auth_type="employer",
            is_admin=False,
            is_applicant=False,
            is_employer_integration=False,
            is_employer=True,
            is_application=False,
            id="hh_user_123",
            first_name="John",
            last_name="Doe",
            email="john.doe@example.com",
        )

    with patch.object(hh_oauth2_adapter._client, "get", _http_call):  # pyright: ignore[reportPrivateUsage]
        resp = await hh_oauth2_adapter.get_current_user_info(
            oauth2_protocol.OAuth2UserInfoProtocol.GetCurrentUserInfoRequest(access_token="token")
        )
    assert resp.hh_manager_id == "hh_user_123"
    assert resp.name == "John Doe"
    assert resp.email == "john.doe@example.com"


@pytest.mark.asyncio
async def test_hh_oauth2_adapter_get_current_user_info_validates_response(
    hh_oauth2_adapter: hh_adapter.HHOAuth2Adapter,
) -> None:
    """Test that get_current_user_info validates response."""

    async def _http_call(
        *_: Any,  # pyright: ignore[reportExplicitAny]
        response_model: type[hhapi.models.MeManagerProfile],
        **__: Any,  # pyright: ignore[reportExplicitAny, reportAny, reportUnusedParameter]
    ) -> hhapi.models.MeManagerProfile:
        assert response_model is hhapi.models.MeManagerProfile
        raise oauth2_protocol.OAuth2ValidateError("invalid user info response")

    with patch.object(hh_oauth2_adapter._client, "get", _http_call):  # pyright: ignore[reportPrivateUsage]
        with pytest.raises(oauth2_protocol.OAuth2ValidateError):
            _ = await hh_oauth2_adapter.get_current_user_info(
                oauth2_protocol.OAuth2UserInfoProtocol.GetCurrentUserInfoRequest(access_token="token")
            )
