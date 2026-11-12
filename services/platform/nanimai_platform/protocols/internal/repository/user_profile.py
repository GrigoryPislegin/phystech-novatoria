from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import EmailStr

from nanimai_platform.domain.scalar import ProjectID, UserID
from nanimai_platform.domain.user_profile import UserProfile
from nanimai_platform.domain.user_profile.user_profile import Tariff, Tutorials


class UserRepositoryError(Exception): ...


class UserValidateError(UserRepositoryError): ...


class UserLoginNotUniqueError(UserRepositoryError): ...


class UserNotFoundError(UserRepositoryError): ...


class CreateUserError(UserRepositoryError): ...


class ReadUserError(UserRepositoryError): ...


class UpdateUserError(UserRepositoryError): ...


class DeleteUserError(UserRepositoryError): ...


class UserRepositoryProtocol(ABC):
    @dataclass
    class CreateUserProfileRequest:
        email: EmailStr
        name: str
        password: str
        thumbnail_url: str
        tariff: Tariff
        tutorials: Tutorials

    @abstractmethod
    async def create_user_profile(self, request: CreateUserProfileRequest) -> UserProfile:
        """creates user in repository

        Raises:
            CreateUserError - not expected exception
            UserValidateError - validation error
            UserLoginNotUniqueError - login of user is already used
        Returns:
            User - created user
        """
        ...

    @dataclass
    class ReadUserProfileRequest:
        id: UserID

    @abstractmethod
    async def read_user_profile(self, request: ReadUserProfileRequest) -> UserProfile:
        """reads user in repository

        Raises:
            ReadUserError - not expected exception
            UserValidateError - validation error
            UserNotFoundError - user not found
        Returns:
            User - read user
        """
        ...

    @dataclass
    class UpdateUserProfileRequest:
        id: UserID
        email: EmailStr | None = None
        name: str | None = None
        password: str | None = None
        thumbnail_url: str | None = None
        tariff: Tariff | None = None
        tutorials: Tutorials | None = None
        projects: list[ProjectID] | None = None

    @abstractmethod
    async def update_user_profile(self, request: UpdateUserProfileRequest) -> UserProfile:
        """updates user in repository

        Raises:
            UpdateUserError - not expected exception
            UserValidateError - validation error
            UserNotFoundError - user not found
        Returns:
            User - updated user
        """
        ...

    @dataclass
    class DeleteUserProfileRequest:
        id: UserID

    @abstractmethod
    async def delete_user_profile(self, request: DeleteUserProfileRequest) -> UserProfile:
        """deletes user in repository

        Raises:
            DeleteUserError - not expected exception
            UserValidateError - validation error
            UserNotFoundError - user not found
        Returns:
            User - deleted user
        """
        ...

    @dataclass
    class ReadManyUserProfilesRequest:
        user_ids: list[UserID]

    @abstractmethod
    async def read_many_user_profiles(self, request: ReadManyUserProfilesRequest) -> list[UserProfile | None]:
        """reads many users in repository

        Raises:
            ReadUserError - not expected exception
            UserValidateError - validation error
            UserNotFoundError - user not found
        Returns:
            list[User | None] - list of users or None if user does not exist
        """
        ...

    @dataclass
    class ReadUserProfileByEmailRequest:
        email: EmailStr

    @abstractmethod
    async def read_user_profile_by_email(self, request: ReadUserProfileByEmailRequest) -> UserProfile:
        """reads user in repository by email

        Raises:
            ReadUserError - not expected exception
            UserValidateError - validation error
            UserNotFoundError - user not found
        Returns:
            User - read user
        """
        ...

    @abstractmethod
    async def read_all_user_profiles(self) -> list[UserProfile]:
        """reads all users in repository

        Raises:
            ReadUserError - not expected exception
            UserValidateError - validation error
        Returns:
            list[User] - list of users
        """
        ...
