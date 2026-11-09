import functools
import traceback
from datetime import UTC, datetime, timedelta
from typing import Any, override
from urllib.parse import urlencode

import httpx
import pydantic
import structlog

from nanimai_platform.domain import Token
from nanimai_platform.protocols.external.oauth2 import (
    OAuth2APIError,
    OAuth2Error,
    OAuth2Protocol,
    OAuth2ValidateError,
)

log = structlog.stdlib.get_logger("app.adapters.HHOAuth2Adapter")


class HHOAuth2Adapter(OAuth2Protocol):
    def __init__(
        self,
        redirect_url: str,
        client_id: str,
        client_secret: str,
        user_agent: str,
        app_url: str | None = None,
    ):
        self.user_agent = user_agent
        self._redirect_url = redirect_url
        self._client_id = client_id
        self._client_secret = client_secret

        self._api_client = httpx.AsyncClient(
            headers={"User-Agent": self.user_agent},
            timeout=30.0,
        )
        self.R = self._api_client.build_request
        self.GET = functools.partial(self.R, "GET")
        self.POST = functools.partial(self.R, "POST")

    async def aclose(self) -> None:
        await self._api_client.aclose()

    async def run(self, request: httpx.Request) -> dict[str, Any]:
        try:
            response = await self._api_client.send(request)
            response.raise_for_status()

            try:
                data = response.json()
                return data
            except Exception as e:
                log.error("failed to decode response", response=response.text[:500])
                raise OAuth2APIError(f"Failed to parse JSON response: {response.text[:500]}") from e
        except httpx.HTTPStatusError as e:
            r = e.response
            log.error(
                "HTTP error in HH API request",
                status_code=e.response.status_code,
                error=str(e),
                response_text=e.response.text[:500],
            )
            raise OAuth2APIError("HTTP error in HH API", r.status_code, r.text[:500]) from e
        except httpx.RequestError as e:
            log.error(
                "Request error in HH API call",
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )
            raise OAuth2APIError("Request error in HH API") from e
        except OAuth2APIError as e:
            log.error("failed due to API error", err=e)
            raise e
        except Exception as e:
            log.error(
                "Unexpected error in HH API call",
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )
            raise OAuth2APIError("Unexpected error in HH API") from e

    @override
    def generate_oauth_link(
        self, request: OAuth2Protocol.GenerateOAuthLinkRequest
    ) -> OAuth2Protocol.GenerateOAuthLinkResponse:
        try:
            hh_auth_url = "https://hh.ru/oauth/authorize"
            redirect_b = f"{self._redirect_url}/api/v1/hh/complete"

            query = {
                "response_type": "code",
                "client_id": self._client_id,
                "redirect_uri": redirect_b,
                "state": request.state,
            }

            redirect_c = f"{hh_auth_url}?{urlencode(query)}"
            return OAuth2Protocol.GenerateOAuthLinkResponse(
                redirect_back=redirect_c,
            )
        except Exception as e:
            raise OAuth2Error("Unexpected error") from e

    @staticmethod
    def _parse_token_response(response: dict[str, Any]) -> Token:
        try:
            exp_in = response.get("expires_in")
            access = response.get("access_token")
            token_type = response.get("token_type")
            refresh = response.get("refresh_token")

            if not (isinstance(exp_in, int) or isinstance(exp_in, float)):
                raise ValueError("expires_in invalid")
            if not isinstance(access, str):
                raise ValueError("access_token invalid")
            if not isinstance(token_type, str):
                raise ValueError("token_type invalid")
            if not isinstance(refresh, str):
                raise ValueError("refresh_token invalid")

            exp_in = int(exp_in)
            token = Token(
                access_token=access,
                expires_in=exp_in,
                expires_at=datetime.now(UTC) + timedelta(seconds=exp_in),
                token_type=token_type,
                refresh_token=refresh,
            )
            return token
        except ValueError as e:
            raise OAuth2ValidateError("invalid token response") from e

    @override
    async def get_token_by_secret_code(
        self, request: OAuth2Protocol.GetTokensBySecretCodeRequest
    ) -> OAuth2Protocol.TokenResponse:
        try:
            hh_token_url = "https://api.hh.ru/token"
            payload = {
                "grant_type": "authorization_code",
                "code": request.secret_code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": f"{self._redirect_url}/api/v1/hh/complete",
            }

            response = await self.run(
                self.POST(
                    hh_token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            )
            return OAuth2Protocol.TokenResponse(token=self._parse_token_response(response))
        except OAuth2ValidateError as e:
            raise e
        except pydantic.ValidationError:
            raise OAuth2ValidateError("validation error") from None
        except OAuth2APIError as e:
            raise e
        except Exception:
            raise OAuth2Error("Unexpected error") from None

    @override
    async def refresh_tokens(self, request: OAuth2Protocol.RefreshTokensRequest) -> OAuth2Protocol.TokenResponse:
        try:
            hh_token_url = "https://api.hh.ru/token"

            response = await self.run(
                self.POST(
                    hh_token_url,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": request.refresh_token,
                    },
                )
            )
            return OAuth2Protocol.TokenResponse(token=self._parse_token_response(response))
        except OAuth2ValidateError as e:
            raise e
        except pydantic.ValidationError:
            raise OAuth2ValidateError("validation error") from None
        except OAuth2APIError as e:
            raise e
        except Exception:
            raise OAuth2Error("Unexpected error") from None
