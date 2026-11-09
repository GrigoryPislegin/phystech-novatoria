from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from nanimai_platform.domain import Oauth2SourceEnum, Token, UserID
from nanimai_platform.protocols.external.oauth2 import OAuth2Protocol
from nanimai_platform.protocols.internal import repository as protocol
from nanimai_platform.services.oauth2.service import OAuth2Service
from nanimai_platform.tests.conftest import make_oauth2_profile


@pytest.mark.asyncio
async def test_init_oauth_flow_generate_hh_link_creates_profile(make_oauth2_service) -> None:
    env = make_oauth2_service()
    svc: OAuth2Service = env.svc

    user_id = UserID("507f1f77bcf86cd799439011")
    redirect_back = "https://example.com/after"

    def _gen_link(req):
        assert req.state
        return OAuth2Protocol.GenerateOAuthLinkResponse(
            redirect_back=f"https://hh.ru/oauth/authorize?state={req.state}"
        )

    env.hh.generate_oauth_link.side_effect = _gen_link

    resp = await svc.generate_hh_link(OAuth2Service.GenerateHHLinkRequest(redirect_back=redirect_back, user_id=user_id))
    assert "https://hh.ru/oauth/authorize?state=" in resp.redirect_back
    env.repo.create_oauth2_profile.assert_awaited()


@pytest.mark.skip(
    reason="TODO: Режим 'создавать профиль только после успешного обмена токена' - для будущей реализации"
)  # сделать до 28.12.25, возможно уже сделано
@pytest.mark.asyncio
async def test_init_oauth_flow_generate_hh_link_does_not_create_profile_when_disabled(make_oauth2_service) -> None:
    env = make_oauth2_service()
    svc: OAuth2Service = env.svc

    user_id = UserID("507f1f77bcf86cd799439011")
    redirect_back = "https://example.com/after"

    def _gen_link(req):
        assert req.state
        return OAuth2Protocol.GenerateOAuthLinkResponse(
            redirect_back=f"https://hh.ru/oauth/authorize?state={req.state}"
        )

    env.hh.generate_oauth_link.side_effect = _gen_link

    resp = await svc.generate_hh_link(OAuth2Service.GenerateHHLinkRequest(redirect_back=redirect_back, user_id=user_id))
    assert "https://hh.ru/oauth/authorize?state=" in resp.redirect_back
    env.repo.create_oauth2_profile.assert_not_awaited()


@pytest.mark.asyncio
async def test_exchange_secret_code_stores_encrypted_tokens(make_oauth2_service) -> None:
    env = make_oauth2_service()
    svc: OAuth2Service = env.svc
    user_id = UserID("507f1f77bcf86cd799439011")

    now = datetime.now(UTC)
    returned = Token(
        access_token="access",
        refresh_token="refresh",
        expires_in=3600,
        expires_at=now + timedelta(seconds=3600),
        token_type="bearer",
    )

    env.hh.get_token_by_secret_code.return_value = OAuth2Protocol.TokenResponse(token=returned)

    async def _update(req):
        assert req.token.access_token.startswith("enc:")
        assert req.token.refresh_token.startswith("enc:")
        return make_oauth2_profile(user_id=req.user_id, source=req.source, token=req.token)

    env.repo.update_oauth2_profile.side_effect = _update

    out = await svc.store_token_by_secret_code(
        OAuth2Service.StoreTokenBySecretCodeRequest(user_id=user_id, source=Oauth2SourceEnum.HH, secret_code="CODE")
    )
    assert out.user_id == user_id
    assert out.source == Oauth2SourceEnum.HH
    assert out.token is not None
    assert out.token.access_token == "access"
    assert out.token.refresh_token == "refresh"


@pytest.mark.asyncio
async def test_complete_oauth_flow_store_secret_code_returns_redirect_even_if_exchange_failed(
    make_oauth2_service,
) -> None:
    env = make_oauth2_service()
    svc: OAuth2Service = env.svc

    user_id = UserID("507f1f77bcf86cd799439011")
    redirect_back = "https://example.com/after"
    state = svc._generate_state(OAuth2Service.GenerateHHLinkRequest(redirect_back=redirect_back, user_id=user_id))  # noqa: SLF001

    env.hh.get_token_by_secret_code = AsyncMock(side_effect=RuntimeError("hh down"))

    resp = await svc.store_secret_code(
        OAuth2Service.StoreSecretCodeRequest(source=Oauth2SourceEnum.HH, state=state, secret_code="CODE")
    )
    assert resp.redirect_back == redirect_back


@pytest.mark.skip(
    reason="TODO: Режим 'создавать профиль только после успешного обмена токена' - для будущей реализации"
)  # сделать до 28.12.25, возможно уже сделано
@pytest.mark.asyncio
async def test_complete_oauth_flow_without_precreated_profile_creates_profile_on_exchange(
    make_oauth2_service,
    background_task_group,
) -> None:
    env = make_oauth2_service()
    svc: OAuth2Service = env.svc

    user_id = UserID("507f1f77bcf86cd799439011")
    redirect_back = "https://example.com/after"

    def _gen_link(req):
        assert req.state
        return OAuth2Protocol.GenerateOAuthLinkResponse(
            redirect_back=f"https://hh.ru/oauth/authorize?state={req.state}"
        )

    env.hh.generate_oauth_link.side_effect = _gen_link

    gen = await svc.generate_hh_link(OAuth2Service.GenerateHHLinkRequest(redirect_back=redirect_back, user_id=user_id))
    env.repo.create_oauth2_profile.assert_not_awaited()
    state = gen.redirect_back.split("state=", 1)[1]

    now = datetime.now(UTC)
    returned = Token(
        access_token="access",
        refresh_token="refresh",
        expires_in=3600,
        expires_at=now + timedelta(seconds=3600),
        token_type="bearer",
    )
    env.hh.get_token_by_secret_code.return_value = OAuth2Protocol.TokenResponse(token=returned)

    env.repo.update_oauth2_profile.side_effect = protocol.OAuth2NotFoundError()

    async def _create(req):
        assert req.token is not None
        assert req.token.access_token.startswith("enc:")
        assert req.token.refresh_token.startswith("enc:")
        return make_oauth2_profile(user_id=req.user_id, source=req.source, token=req.token)

    env.repo.create_oauth2_profile.side_effect = _create

    resp = await svc.store_secret_code(
        OAuth2Service.StoreSecretCodeRequest(source=Oauth2SourceEnum.HH, state=state, secret_code="CODE")
    )
    assert resp.redirect_back == redirect_back
    env.repo.create_oauth2_profile.assert_awaited()
    env.queue.upsert_token.assert_awaited()

    await background_task_group.wait()


@pytest.mark.asyncio
async def test_obtain_access_token_retrieve_token_decrypts_from_repo(make_oauth2_service) -> None:
    env = make_oauth2_service()
    svc: OAuth2Service = env.svc
    user_id = UserID("507f1f77bcf86cd799439011")

    now = datetime.now(UTC)
    enc = Token(
        access_token="enc:access",
        refresh_token="enc:refresh",
        expires_in=3600,
        expires_at=now + timedelta(seconds=3600),
        token_type="bearer",
    )
    env.repo.read_oauth2_profile.return_value = make_oauth2_profile(
        user_id=user_id, source=Oauth2SourceEnum.HH, token=enc
    )

    out = await svc.retrieve_token(OAuth2Service.RetrieveTokenRequest(user_id=user_id, source=Oauth2SourceEnum.HH))
    assert out.token is not None
    assert out.token.access_token == "access"
    assert out.token.refresh_token == "refresh"


@pytest.mark.asyncio
async def test_refresh_headhunter_tokens_renew_token_refreshes_and_upserts_queue(
    make_oauth2_service,
    background_task_group,
) -> None:
    env = make_oauth2_service()
    svc: OAuth2Service = env.svc
    user_id = UserID("507f1f77bcf86cd799439011")

    now = datetime.now(UTC)
    stored_enc = Token(
        access_token="enc:old_access",
        refresh_token="enc:old_refresh",
        expires_in=3600,
        expires_at=now + timedelta(seconds=3600),
        token_type="bearer",
    )
    env.repo.read_oauth2_profile.return_value = make_oauth2_profile(
        user_id=user_id, source=Oauth2SourceEnum.HH, token=stored_enc
    )

    refreshed = Token(
        access_token="new_access",
        refresh_token="new_refresh",
        expires_in=1800,
        expires_at=now + timedelta(seconds=1800),
        token_type="bearer",
    )
    env.hh.refresh_tokens.return_value = OAuth2Protocol.TokenResponse(token=refreshed)

    async def _update(req):
        assert req.token.access_token == "enc:new_access"
        assert req.token.refresh_token == "enc:new_refresh"
        return make_oauth2_profile(user_id=req.user_id, source=req.source, token=req.token)

    env.repo.update_oauth2_profile.side_effect = _update

    out = await svc.renew_token(OAuth2Service.RenewTokenRequest(user_id=user_id, source=Oauth2SourceEnum.HH))
    assert out.token is not None
    assert out.token.access_token == "new_access"
    assert out.token.refresh_token == "new_refresh"
    env.queue.upsert_token.assert_awaited()
    await background_task_group.wait()
