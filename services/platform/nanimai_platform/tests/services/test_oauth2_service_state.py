from __future__ import annotations

import pytest

from nanimai_platform.domain import UserID
from nanimai_platform.services.crypt.service import CryptServiceInvalidDataError
from nanimai_platform.services.oauth2.service import OAuth2Service


@pytest.mark.asyncio
async def test_encrypt_oauth_state_roundtrip(make_oauth2_service) -> None:
    env = make_oauth2_service()
    svc: OAuth2Service = env.svc

    user_id = UserID("507f1f77bcf86cd799439011")
    redirect_back = "https://example.com/callback?x=1&y=2"

    state = svc._generate_state(OAuth2Service.GenerateHHLinkRequest(redirect_back=redirect_back, user_id=user_id))  # noqa: SLF001
    parsed = svc._parse_state(OAuth2Service.ParseStateRequest(state=state))  # noqa: SLF001
    assert parsed.user_id == user_id
    assert parsed.redirect_back == redirect_back


@pytest.mark.asyncio
async def test_encrypt_oauth_state_empty_state_raises(make_oauth2_service) -> None:
    env = make_oauth2_service()
    svc: OAuth2Service = env.svc

    with pytest.raises(CryptServiceInvalidDataError):
        _ = svc._parse_state(OAuth2Service.ParseStateRequest(state=""))  # noqa: SLF001
