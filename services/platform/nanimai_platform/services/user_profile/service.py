import asyncio
from typing import final

import structlog
from pydantic import BaseModel, EmailStr

from nanimai_platform.domain.scalar.scalars import ProjectID, UserID
from nanimai_platform.domain.user_profile.user_profile import Tariff, Tutorials, UserProfile
from nanimai_platform.protocols.internal.repository import user_profile as protocol
from nanimai_platform.services.cache.cache import Cache
from nanimai_platform.services.cache.keyspace import Keyspace

log = structlog.stdlib.get_logger("app.service.UserService")


class UserServiceError(Exception): ...


class UserServiceInvalidDataError(UserServiceError): ...


class UserServiceNotUniqueLoginError(UserServiceError): ...


class UserServiceUserNotFoundError(UserServiceError): ...


@final
class UserService:
    def __init__(self, cache: Cache, user_repo: protocol.UserRepositoryProtocol):
        self._ks = Keyspace("user_service")
        self._cache = cache

        self._user_repo = user_repo

    class CreateUserProfileRequest(BaseModel):
        email: EmailStr
        name: str
        password: str
        thumbnail_url: str
        tariff: Tariff
        tutorials: Tutorials

    async def create(self, request: CreateUserProfileRequest) -> UserProfile:
        # check if already exists
        try:
            # try to read from cache
            user = await self._cache.get(self._ks.key("email", str(request.email)), t=UserProfile)

            if user is None:
                # in case of cache miss, try to read from db
                user = await self._user_repo.read_user_profile_by_email(
                    protocol.UserRepositoryProtocol.ReadUserProfileByEmailRequest(email=request.email)
                )
        except protocol.UserNotFoundError:
            # in case of db miss, return None
            user = None
        except Exception as e:
            log.error(f"failed to read user with error {e}")
            raise UserServiceError("unknown error") from e

        if user is not None:
            raise UserServiceNotUniqueLoginError("user with email already exists")

        try:
            new_user = await self._user_repo.create_user_profile(
                protocol.UserRepositoryProtocol.CreateUserProfileRequest(
                    email=request.email,
                    name=request.name,
                    password=request.password,
                    thumbnail_url=request.thumbnail_url,
                    tariff=request.tariff,
                    tutorials=request.tutorials,
                )
            )

            # set user in cache
            asyncio.create_task(self._cache.set(self._ks.key("email", request.email), new_user))
            asyncio.create_task(self._cache.set(self._ks.key("id", str(new_user.id)), new_user))

            return new_user
        except protocol.UserValidateError as e:
            log.error("failed with validation error", err=e)
            raise UserServiceInvalidDataError("invalid data") from e
        except protocol.CreateUserError as e:
            log.error("failed with error", err=e)
            raise UserServiceError("user creation failed") from e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise UserServiceError("unknown error") from e

    class ReadUserProfileRequest(BaseModel):
        id: UserID

    async def read(self, request: ReadUserProfileRequest) -> UserProfile:
        try:
            if (user := await self._cache.get(self._ks.key("id", str(request.id)), t=UserProfile)) is not None:
                return user

            user = await self._user_repo.read_user_profile(
                protocol.UserRepositoryProtocol.ReadUserProfileRequest(id=request.id)
            )

            asyncio.create_task(self._cache.set(self._ks.key("id", str(user.id)), user))

            return user
        except protocol.UserValidateError as e:
            log.error("failed with validation error", err=e)
            raise UserServiceInvalidDataError("invalid data") from e
        except protocol.UserNotFoundError as e:
            log.error("failed to find user", err=e)
            raise UserServiceUserNotFoundError("failed to find") from e
        except protocol.ReadUserError as e:
            log.error("failed with error", err=e)
            raise UserServiceError("user read failed") from e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise UserServiceError("unknown error") from e

    class ReadManyUserProfilesRequest(BaseModel):
        user_ids: list[UserID]

    async def read_many(self, request: ReadManyUserProfilesRequest) -> list[UserProfile | None]:
        try:
            if len(request.user_ids) == 0:
                return []

            users: dict[UserID, UserProfile] = {}

            # try to load as much as possible from cache
            cache_users = await asyncio.gather(*[
                self._cache.get(self._ks.key("id", str(user_id)), t=UserProfile) for user_id in request.user_ids
            ])
            for user in cache_users:
                if user is not None:
                    users[user.id] = user  # store results

            # retrieve from db the rest
            retrieve_from_db = list(set(request.user_ids) - set(users.keys()))

            db_users = await self._user_repo.read_many_user_profiles(
                protocol.UserRepositoryProtocol.ReadManyUserProfilesRequest(user_ids=retrieve_from_db)
            )
            for user in db_users:
                if user is not None:
                    users[user.id] = user

            # save users to cache
            for user in users.values():
                asyncio.create_task(self._cache.set(self._ks.key("id", str(user.id)), user))

            # return users in the same order as requested
            return [users.get(user_id, None) for user_id in request.user_ids]
        except protocol.UserValidateError as e:
            log.error("failed with validation error", err=e)
            raise UserServiceInvalidDataError("invalid data") from e
        except protocol.ReadUserError as e:
            log.error("failed with error", err=e)
            raise UserServiceError("user read failed") from e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise UserServiceError("unknown error") from e

    class ReadUserProfileByEmailRequest(BaseModel):
        email: EmailStr

    async def read_by_email(self, request: ReadUserProfileByEmailRequest) -> UserProfile:
        try:
            if (user := await self._cache.get(self._ks.key("email", request.email), t=UserProfile)) is not None:
                return user

            user = await self._user_repo.read_user_profile_by_email(
                protocol.UserRepositoryProtocol.ReadUserProfileByEmailRequest(email=request.email)
            )
            asyncio.create_task(self._cache.set(self._ks.key("email", request.email), user))

            return user
        except protocol.UserValidateError as e:
            log.error("failed with validation error", err=e)
            raise UserServiceInvalidDataError("invalid data") from e
        except protocol.UserNotFoundError as e:
            log.error("failed to find user", err=e)
            raise UserServiceUserNotFoundError("failed to find") from e
        except protocol.ReadUserError as e:
            log.error("failed with error", err=e)
            raise UserServiceError("user read failed") from e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise UserServiceError("unknown error") from e

    class UpdateUserProfileRequest(BaseModel):
        id: UserID
        email: EmailStr | None = None
        name: str | None = None
        password: str | None = None
        thumbnail_url: str | None = None
        tariff: Tariff | None = None
        tutorial_platform: bool | None = None
        tutorial_interview: bool | None = None
        projects: list[ProjectID] | None = None

    async def update(self, request: UpdateUserProfileRequest) -> UserProfile:
        try:
            tutorials_update = None
            if request.tutorial_platform is not None or request.tutorial_interview is not None:
                user = await self.read(self.ReadUserProfileRequest(id=request.id))
                tutorials_update = Tutorials(
                    platform=request.tutorial_platform or user.tutorials.platform,
                    interview=request.tutorial_interview or user.tutorials.interview,
                )

            user = await self._user_repo.update_user_profile(
                protocol.UserRepositoryProtocol.UpdateUserProfileRequest(
                    id=request.id,
                    email=request.email,
                    name=request.name,
                    password=request.password,
                    thumbnail_url=request.thumbnail_url,
                    tariff=request.tariff,
                    tutorials=tutorials_update,
                    projects=request.projects,
                )
            )

            asyncio.create_task(self._cache.set(self._ks.key("id", str(user.id)), user))
            asyncio.create_task(self._cache.set(self._ks.key("email", user.email), user))

            return user

        except protocol.UserValidateError as e:
            log.error("failed with validation error", err=e)
            raise UserServiceInvalidDataError("invalid data") from e
        except protocol.UserNotFoundError as e:
            log.error("failed to find user", err=e)
            raise UserServiceUserNotFoundError("failed to find") from e
        except protocol.UpdateUserError as e:
            log.error("failed with error", err=e)
            raise UserServiceError("user update failed") from e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise UserServiceError("unknown error") from e

    class DeleteUserProfileRequest(BaseModel):
        id: UserID

    async def delete(self, request: DeleteUserProfileRequest) -> UserProfile:
        try:
            user = await self._user_repo.delete_user_profile(
                protocol.UserRepositoryProtocol.DeleteUserProfileRequest(id=request.id)
            )
            await self._cache.invalidate(self._ks.key("id", str(user.id)))
            await self._cache.invalidate(self._ks.key("email", user.email))

            return user
        except protocol.UserValidateError as e:
            log.error("failed with validation error", err=e)
            raise UserServiceInvalidDataError("invalid data") from e
        except protocol.UserNotFoundError as e:
            log.error("failed to find user", err=e)
            raise UserServiceUserNotFoundError("failed to find") from e
        except protocol.DeleteUserError as e:
            log.error("failed with error", err=e)
            raise UserServiceError("user delete failed") from e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise UserServiceError("unknown error") from e

    async def read_all(self) -> list[UserProfile]:
        # не кешировать
        try:
            db_users = await self._user_repo.read_all_user_profiles()
            return db_users
        except protocol.UserValidateError as e:
            log.error("failed with validation error", err=e)
            raise UserServiceInvalidDataError("invalid data") from e
        except protocol.ReadUserError as e:
            log.error("failed with error", err=e)
            raise UserServiceError("user read failed") from e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise UserServiceError("unknown error") from e
