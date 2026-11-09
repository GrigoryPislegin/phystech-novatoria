from abc import ABC, abstractmethod
from dataclasses import dataclass

from nanimai_platform.domain import (
    OAuth2Profile,
    Oauth2SourceEnum,
    Token,
    UserID,
)


class OAuth2RepositoryError(Exception): ...


class OAuth2ValidateError(OAuth2RepositoryError): ...


class OAuth2NotFoundError(OAuth2RepositoryError): ...


class CreateOAuth2Error(OAuth2RepositoryError): ...


class ReadOAuth2Error(OAuth2RepositoryError): ...


class UpdateOAuth2Error(OAuth2RepositoryError): ...


class DeleteOAuth2Error(OAuth2RepositoryError): ...


class OAuth2RepositoryProtocol(ABC):
    @dataclass
    class CreateOAuth2Request:
        user_id: UserID
        source: Oauth2SourceEnum
        token: Token | None = None

    @abstractmethod
    async def create_oauth2_profile(self, request: CreateOAuth2Request) -> OAuth2Profile:
        """creates oauth2 profile in repository

        Raises:
            CreateOAuth2Error - not expected exception
            OAuth2ValidateError - validation error
            UserNotFoundError - user not found
        Returns:
            OAuth2Profile - created oauth2 profile
        """
        ...

    @dataclass
    class ReadOAuth2Request:
        user_id: UserID
        source: Oauth2SourceEnum

    @abstractmethod
    async def read_oauth2_profile(self, request: ReadOAuth2Request) -> OAuth2Profile:
        """reads oauth2 profile in repository

        Raises:
            ReadOAuth2Error - not expected exception
            OAuth2ValidateError - validation error
            OAuth2NotFoundError - oauth2 not found
        Returns:
            OAuth2Profile - read oauth2 profile
        """
        ...

    @dataclass
    class ReadManyOAuth2Request:
        user_id: UserID

    @abstractmethod
    async def read_many_oauth2_profiles(self, request: ReadManyOAuth2Request) -> list[OAuth2Profile]:
        """reads all oauth2 profiles in repository by user

        Raises:
            ReadOAuth2Error - not expected exception
            OAuth2ValidateError - validation error
        Returns:
            list[OAuth2Profile] - list of user's oauth2 profile
        """
        ...

    @dataclass
    class UpdateOAuth2Request:
        user_id: UserID
        source: Oauth2SourceEnum

        token: Token | None = None

    @abstractmethod
    async def update_oauth2_profile(self, request: UpdateOAuth2Request) -> OAuth2Profile:
        """updates oauth2 profile in repository

        Raises:
            UpdateOAuth2Error - not expected exception
            OAuth2ValidateError - validation error
            OAuth2NotFoundError - oauth2 not found
        Returns:
            OAuth2Profile - updated oauth2 profile
        """
        ...

    @dataclass
    class DeleteOAuth2Request:
        user_id: UserID
        source: Oauth2SourceEnum

    @abstractmethod
    async def delete_oauth2_profile(self, request: DeleteOAuth2Request) -> OAuth2Profile:
        """deletes oauth2 profile in repository

        Raises:
            DeleteOAuth2Error - not expected exception
            OAuth2ValidateError - validation error
            OAuth2NotFoundError - oauth2 not found
        Returns:
            OAuth2Profile - deleted oauth2 profile
        """
        ...
