from abc import ABC, abstractmethod
from datetime import datetime

import pydantic


class OAuth2Error(Exception):
    """Base exception for OAuth2 protocol errors."""


class OAuth2ValidateError(OAuth2Error):
    """Validation error in OAuth2 protocol."""


class OAuth2APIError(OAuth2Error):
    """API error in OAuth2 protocol."""


class Token(pydantic.BaseModel):
    """OAuth2 token pair."""

    access_token: str
    refresh_token: str
    expires_in: int
    expires_at: datetime
    token_type: str


class OAuth2Protocol(ABC):
    """Protocol for core OAuth2 operations with HeadHunter (tokens, links)."""

    class GenerateOAuthLinkRequest(pydantic.BaseModel):
        """Request to generate OAuth authorization link."""

        state: str
        redirect_url: str

    class GenerateOAuthLinkResponse(pydantic.BaseModel):
        """Response with OAuth authorization link."""

        redirect_url: str

    @abstractmethod
    def generate_oauth_link(self, request: GenerateOAuthLinkRequest) -> GenerateOAuthLinkResponse: ...

    class GetTokensBySecretCodeRequest(pydantic.BaseModel):
        """Request to exchange secret code for tokens."""

        secret_code: str
        redirect_uri: str

    class TokenResponse(pydantic.BaseModel):
        """Response with OAuth2 tokens."""

        token: Token

    @abstractmethod
    async def get_token_by_secret_code(self, request: GetTokensBySecretCodeRequest) -> TokenResponse: ...

    class RefreshTokensRequest(pydantic.BaseModel):
        """Request to refresh tokens."""

        refresh_token: str

    @abstractmethod
    async def refresh_tokens(self, request: RefreshTokensRequest) -> TokenResponse: ...


class OAuth2UserInfoProtocol(ABC):
    """Protocol for retrieving current user information from HeadHunter."""

    class GetCurrentUserInfoRequest(pydantic.BaseModel):
        """Request to get current user info."""

        access_token: str

    class GetCurrentUserInfoResponse(pydantic.BaseModel):
        """Response with current user info."""

        hh_manager_id: str
        hh_employer_id: str
        name: str
        email: str

    @abstractmethod
    async def get_current_user_info(
        self,
        request: GetCurrentUserInfoRequest,
    ) -> GetCurrentUserInfoResponse: ...
