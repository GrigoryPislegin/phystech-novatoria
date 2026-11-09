from typing import TYPE_CHECKING, cast
from urllib import parse

import pytest

if TYPE_CHECKING:
    from unittest.mock import Mock

    from dishka.async_container import AsyncContainer

from hharon.protocols import oauth2 as oauth2_protocol
from hharon.usecases.oauth2 import InitOAuthFlow


@pytest.mark.asyncio
async def test_init_oauth_flow_generate_hh_link(init_oauth_flow_container: "AsyncContainer") -> None:
    usecase = await init_oauth_flow_container.get(InitOAuthFlow)
    assert isinstance(usecase, InitOAuthFlow)
    hh_adapter = cast("Mock", await init_oauth_flow_container.get(oauth2_protocol.OAuth2Protocol))

    user_id = "507f1f77bcf86cd799439011"
    platform_redirect_url = "https://nanimai.tech/complete"  # Platform after auth URL

    def _gen_link(
        req: oauth2_protocol.OAuth2Protocol.GenerateOAuthLinkRequest,
    ) -> oauth2_protocol.OAuth2Protocol.GenerateOAuthLinkResponse:
        assert req.state
        assert req.redirect_url == platform_redirect_url

        hh_auth_url = "https://hh.ru/oauth/authorize"
        params = {
            "response_type": "code",
            "client_id": "test",
            "state": req.state,
            "redirect_uri": req.redirect_url,
        }
        full_url = f"{hh_auth_url}?{parse.urlencode(params)}"
        return oauth2_protocol.OAuth2Protocol.GenerateOAuthLinkResponse(redirect_url=full_url)

    # Mock's attributes are dynamically typed
    generate_oauth_link_mock = cast("Mock", hh_adapter.generate_oauth_link)
    generate_oauth_link_mock.side_effect = _gen_link

    resp = await usecase.init_oauth_flow(
        InitOAuthFlow.InitOAuthFlowRequest(user_id=user_id, redirect_url=platform_redirect_url)
    )
    assert isinstance(resp, InitOAuthFlow.InitOAuthFlowResponse)

    # Verify response contains HeadHunter authorization URL
    assert resp.redirect_url.startswith("https://hh.ru/oauth/authorize?")
    parsed_url = parse.urlparse(resp.redirect_url)
    params = parse.parse_qs(parsed_url.query)
    assert params["response_type"] == ["code"]
    assert params["client_id"] == ["test"]
    assert params["state"]  # Should contain encrypted state
    assert params["redirect_uri"] == [platform_redirect_url]
