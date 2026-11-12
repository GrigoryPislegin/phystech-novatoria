from abc import ABC, abstractmethod

from pydantic import BaseModel

from nanimai_platform.domain import Token


class OAuth2Error(Exception): ...


class OAuth2ValidateError(OAuth2Error): ...


class OAuth2APIError(OAuth2Error): ...


class OAuth2Protocol(ABC):
    class GenerateOAuthLinkRequest(BaseModel):
        state: str

    class GenerateOAuthLinkResponse(BaseModel):
        redirect_back: str

    @abstractmethod
    def generate_oauth_link(self, request: GenerateOAuthLinkRequest) -> GenerateOAuthLinkResponse:
        """generate OAuth link

        Raises:
            OAuth2Error - unexpected error
        Returns:
            GenerateOAuthLinkResponse: redirect back uri
        """
        ...

    class GetTokensBySecretCodeRequest(BaseModel):
        secret_code: str

    class TokenResponse(BaseModel):
        token: Token

    @abstractmethod
    async def get_token_by_secret_code(self, request: GetTokensBySecretCodeRequest) -> TokenResponse:
        """get access and refresh tokens by secret code

        Raises:
            OAuth2APIError - error with external api
            OAuth2ValidateError - wrong data error
            OAuth2Error - unexpected error
        Returns:
            GetTokensBySecretCodeResponse: access and refresh tokens
        """
        ...

    class RefreshTokensRequest(BaseModel):
        refresh_token: str

    @abstractmethod
    async def refresh_tokens(self, request: RefreshTokensRequest) -> TokenResponse:
        """refresh tokens

        Raises:
            OAuth2APIError - error with external api
            OAuth2ValidateError - wrong data error
            OAuth2Error - unexpected error
        Returns:
            RefreshTokensResponse: access and refresh tokens
        """
        ...
