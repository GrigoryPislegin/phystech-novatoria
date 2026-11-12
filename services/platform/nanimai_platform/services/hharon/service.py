from __future__ import annotations

from typing import final

import structlog
from pydantic import BaseModel

from nanimai_platform.domain import UserID
from nanimai_platform.protocols.external.hharon import (
    HHaronError,
    HHaronGRPCError,
    HHaronProtocol,
    HHaronValidateError,
)
from nanimai_platform.utils.logging_span import span
from nanimai_platform.utils.map_grpc_error import AdvancedGRPCError

log = structlog.stdlib.get_logger("app.service.HHaronService")


class HHaronServiceError(Exception): ...


class HHaronServiceInvalidDataError(HHaronServiceError): ...


class HHaronServiceHHaronGRPCError(AdvancedGRPCError): ...


@final
class HHaronService:
    def __init__(
        self,
        hharon_adapter: HHaronProtocol,
    ):
        self._hharon_adapter = hharon_adapter

    class GetHHaronUserRequest(BaseModel):
        user_id: UserID

    class GetHHaronUserResponse(BaseModel):
        user_id: UserID
        hh_id: str
        name: str
        email: str

    @span(op="hharon_service", name="get_hharon_user")
    async def get_hharon_user(self, request: GetHHaronUserRequest) -> GetHHaronUserResponse:
        try:
            response = await self._hharon_adapter.get_user(HHaronProtocol.GetUserRequest(user_id=request.user_id))

            hharon_user = self.GetHHaronUserResponse(
                user_id=response.user_id,
                hh_id=response.hh_id,
                name=response.name,
                email=response.email,
            )

            return hharon_user
        except HHaronValidateError as e:
            log.error("Failed to get hharon user due to validation error", err=e)
            raise HHaronServiceInvalidDataError("invalid data") from e
        except HHaronGRPCError as e:
            log.error("Failed to get hharon user due to GRPC error", err=e)
            raise HHaronServiceHHaronGRPCError.from_adv(e) from e
        except HHaronError as e:
            log.error("Failed to get hharon user due to HHaron error", err=e)
            raise HHaronServiceError("Failed to get hharon user") from e
        except Exception as e:
            log.exception("Failed to get hharon user", err=e)
            raise HHaronServiceError("Unexpected error") from e
