from datetime import UTC, datetime, timedelta
from typing import final, override
from urllib import parse

import structlog

from hharon.infra.headhunter import HHClientError, HeadHunterClient
from hharon.infra.oauth2 import HHOAuth2Config
from hharon.pkg import hhapi
from hharon.protocols import oauth2 as oauth2_protocol

log = structlog.stdlib.get_logger("hharon.adapters.HHOAuth2Adapter")


@final
class HHOAuth2Adapter(oauth2_protocol.OAuth2Protocol, oauth2_protocol.OAuth2UserInfoProtocol):
    def __init__(self, *, config: HHOAuth2Config, client: HeadHunterClient) -> None:
        self._client_id = config.client_id
        self._client_secret = config.client_secret
        self._client = client

    @staticmethod
    def _parse_token_response(response: hhapi.models.AuthUserToken) -> oauth2_protocol.Token:
        return oauth2_protocol.Token(
            access_token=response.access_token,
            expires_in=response.expires_in,
            expires_at=datetime.now(UTC) + timedelta(seconds=response.expires_in),
            token_type=response.token_type,
            refresh_token=response.refresh_token,
        )

    @override
    def generate_oauth_link(
        self, request: oauth2_protocol.OAuth2Protocol.GenerateOAuthLinkRequest
    ) -> oauth2_protocol.OAuth2Protocol.GenerateOAuthLinkResponse:
        hh_auth_url = "https://hh.ru/oauth/authorize"
        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "state": request.state,
            "redirect_uri": request.redirect_url,
        }
        full_url = f"{hh_auth_url}?{parse.urlencode(params)}"
        return oauth2_protocol.OAuth2Protocol.GenerateOAuthLinkResponse(redirect_url=full_url)

    @override
    async def get_token_by_secret_code(
        self, request: oauth2_protocol.OAuth2Protocol.GetTokensBySecretCodeRequest
    ) -> oauth2_protocol.OAuth2Protocol.TokenResponse:
        try:
            response = await self._client.post(
                "/token",
                data=hhapi.models.AuthCode(
                    grant_type="authorization_code",
                    redirect_uri=request.redirect_uri,
                    code=request.secret_code,
                    client_id=self._client_id,
                    client_secret=self._client_secret,
                ),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                response_model=hhapi.models.AuthUserToken,
            )
            return oauth2_protocol.OAuth2Protocol.TokenResponse(token=self._parse_token_response(response))
        except HHClientError:
            raise
        except oauth2_protocol.OAuth2Error:
            raise
        except Exception as e:
            log.exception("Unexpected error in get_token_by_secret_code", error=str(e), error_type=type(e).__name__)
            raise oauth2_protocol.OAuth2Error("Unexpected error") from e

    @override
    async def refresh_tokens(
        self, request: oauth2_protocol.OAuth2Protocol.RefreshTokensRequest
    ) -> oauth2_protocol.OAuth2Protocol.TokenResponse:
        try:
            response = await self._client.post(
                "/token",
                data=hhapi.models.AuthRefreshToken(
                    grant_type="refresh_token",
                    refresh_token=request.refresh_token,
                ),
                response_model=hhapi.models.AuthUserToken,
            )
            return oauth2_protocol.OAuth2Protocol.TokenResponse(token=self._parse_token_response(response))
        except HHClientError:
            raise
        except oauth2_protocol.OAuth2Error:
            raise
        except Exception as e:
            log.exception("Unexpected error in refresh_tokens", error=str(e), error_type=type(e).__name__)
            raise oauth2_protocol.OAuth2Error("Unexpected error") from e

    @override
    async def get_current_user_info(
        self, request: oauth2_protocol.OAuth2UserInfoProtocol.GetCurrentUserInfoRequest
    ) -> oauth2_protocol.OAuth2UserInfoProtocol.GetCurrentUserInfoResponse:
        try:
            response = await self._client.get(
                "/me",
                headers={"Authorization": f"Bearer {request.access_token}"},
                response_model=hhapi.models.MeManagerProfile,
            )

            return oauth2_protocol.OAuth2UserInfoProtocol.GetCurrentUserInfoResponse(
                hh_manager_id=response.manager.id if response.manager else response.id,
                hh_employer_id=response.employer.id if response.employer else response.id,
                name=f"{response.first_name} {response.last_name}".strip(),
                email=response.email or "",
            )

        except HHClientError:
            raise
        except oauth2_protocol.OAuth2Error:
            raise
        except Exception as e:
            log.exception("Unexpected error in get_current_user_info", error=str(e), error_type=type(e).__name__)
            raise oauth2_protocol.OAuth2Error("Unexpected error") from e
