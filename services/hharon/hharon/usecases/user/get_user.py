from typing import final

import pydantic
import structlog

from hharon.domain.user import HharonUser
from hharon.protocols import cache as cache_protocol
from hharon.protocols import user as user_protocol

log = structlog.stdlib.get_logger("hharon.usecases.GetHharonUser")


class GetHharonUserError(Exception):
    """Base exception class for GetHharonUser errors."""


class GetHharonUserNotFoundError(GetHharonUserError):
    """User not found error."""


@final
class GetHharonUser[SessionT]:
    def __init__(
        self,
        *,
        user_repository: user_protocol.HharonUserRepositoryProtocol[SessionT],
        cache: cache_protocol.CacheProtocol,
    ) -> None:
        self._user_repository = user_repository
        self._cache = cache

    class GetHharonUserRequest(pydantic.BaseModel):
        user_id: str

    class GetHharonUserResponse(pydantic.BaseModel):
        user: HharonUser

    def _cache_key(self, user_id: str) -> str:
        return f"hharon:user:{user_id}"

    async def get_user(self, request: GetHharonUserRequest) -> GetHharonUserResponse:
        try:
            cache_key = self._cache_key(user_id=request.user_id)
            if (cached := await self._cache.get(cache_key, unmarshal_as=HharonUser)) is not None:
                return self.GetHharonUserResponse(user=cached)

            async with self._user_repository.context() as session:
                user = await self._user_repository.get_user(
                    session, user_protocol.HharonUserRepositoryProtocol.GetUserRequest(user_id=request.user_id)
                )

            if user is None:
                log.warning("user not found", user_id=request.user_id)
                error_msg = f"User with user_id {request.user_id} not found"
                raise GetHharonUserNotFoundError(error_msg)

            await self._cache.set(cache_key, user)
            return self.GetHharonUserResponse(user=user)
        except GetHharonUserNotFoundError:
            raise
        except Exception as e:
            log.exception("unexpected error in get user", user_id=request.user_id)
            raise GetHharonUserError("unexpected error") from e
