from __future__ import annotations

from unittest.mock import patch

import pytest

from nanimai_platform.adapters.external.oauth2.hh.adapter import HHOAuth2Adapter
from nanimai_platform.protocols.external.oauth2.protocol import OAuth2Protocol, OAuth2ValidateError


@pytest.mark.asyncio
async def test_hh_oauth2_adapter_generate_oauth_link_contains_expected_params(hh_adapter: HHOAuth2Adapter) -> None:
    resp = hh_adapter.generate_oauth_link(OAuth2Protocol.GenerateOAuthLinkRequest(state="STATE"))
    assert "https://hh.ru/oauth/authorize?" in resp.redirect_back
    assert "response_type=code" in resp.redirect_back
    assert "client_id=client" in resp.redirect_back
    assert "state=STATE" in resp.redirect_back
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A9704%2Fapi%2Fv1%2Fhh%2Fcomplete" in resp.redirect_back


@pytest.mark.asyncio
async def test_hh_oauth2_adapter_token_response_validates_types(hh_adapter: HHOAuth2Adapter) -> None:
    async def _run(_req):
        return {"expires_in": "bad"}

    with patch.object(hh_adapter, "run", _run):
        with pytest.raises(OAuth2ValidateError):
            await hh_adapter.get_token_by_secret_code(OAuth2Protocol.GetTokensBySecretCodeRequest(secret_code="CODE"))


@pytest.mark.asyncio
async def test_hh_oauth2_adapter_get_token_by_secret_code_uses_parser(hh_adapter: HHOAuth2Adapter) -> None:
    async def _run(_req):
        return {
            "access_token": "a",
            "refresh_token": "r",
            "token_type": "bearer",
            "expires_in": 10,
        }

    with patch.object(hh_adapter, "run", _run):
        resp = await hh_adapter.get_token_by_secret_code(
            OAuth2Protocol.GetTokensBySecretCodeRequest(secret_code="CODE")
        )
    assert resp.token.access_token == "a"
    assert resp.token.refresh_token == "r"
    assert resp.token.token_type == "bearer"
    assert resp.token.expires_in == 10


@pytest.mark.asyncio
async def test_hh_oauth2_adapter_refresh_tokens_uses_parser(hh_adapter: HHOAuth2Adapter) -> None:
    async def _run(_req):
        return {
            "access_token": "a2",
            "refresh_token": "r2",
            "token_type": "bearer",
            "expires_in": 11,
        }

    with patch.object(hh_adapter, "run", _run):
        resp = await hh_adapter.refresh_tokens(OAuth2Protocol.RefreshTokensRequest(refresh_token="RR"))
    assert resp.token.access_token == "a2"
    assert resp.token.refresh_token == "r2"
    assert resp.token.expires_in == 11
