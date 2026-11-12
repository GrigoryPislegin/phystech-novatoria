from typing import final, override

import pydantic
import structlog
from grpclib.exceptions import GRPCError

from nanimai_platform.domain import UserID
from nanimai_platform.external_clients.hharon.hharon_api.v1 import (
    CompleteOAuthFlowRequest,
    GetUserRequest,
    HharonServiceStub,
    InitOAuthFlowRequest,
)
from nanimai_platform.protocols.external.hharon import (
    HHaronError,
    HHaronGRPCError,
    HHaronProtocol,
    HHaronValidateError,
)
from nanimai_platform.utils import span

log = structlog.stdlib.get_logger("app.adapter.HHaronAdapter")


@final
class GRPCHHaronAdapter(HHaronProtocol):
    def __init__(self, stub: HharonServiceStub):
        self._stub = stub

    @span(op="hharon_adapter", name="init_oauth_flow")
    @override
    async def init_oauth_flow(
        self, request: HHaronProtocol.InitOAuthFlowRequest
    ) -> HHaronProtocol.InitOAuthFlowResponse:
        grpc_request = InitOAuthFlowRequest(
            user_id=request.user_id,
            redirect_url=request.redirect_url,
        )

        try:
            grpc_response = await self._stub.init_o_auth_flow(grpc_request)

            if not grpc_response.authorization_url:
                raise HHaronError("hharon service returned empty redirect URL")

            return HHaronProtocol.InitOAuthFlowResponse(redirect_url=grpc_response.authorization_url)
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise HHaronValidateError("validation error") from e
        except GRPCError as e:
            log.error("failed to init oauth flow with hharon service", err=e)
            raise HHaronGRPCError.from_grpc(e) from e
        except Exception as e:
            log.error("failed to init oauth flow with hharon service", err=e)
            raise HHaronError("failed to init oauth flow") from e

    @span(op="hharon_adapter", name="complete_oauth_flow")
    @override
    async def complete_oauth_flow(
        self, request: HHaronProtocol.CompleteOAuthFlowRequest
    ) -> HHaronProtocol.CompleteOAuthFlowResponse:
        grpc_request = CompleteOAuthFlowRequest(
            secret_code=request.secret_code,
            encrypted_state=request.encrypted_state,
            redirect_uri=request.redirect_uri,
        )

        try:
            grpc_response = await self._stub.complete_o_auth_flow(grpc_request)

            if not grpc_response.success:
                log.warning("hharon oauth flow was not successful")

            return HHaronProtocol.CompleteOAuthFlowResponse(
                user_id=UserID(grpc_response.user_id),
                success=grpc_response.success,
            )
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise HHaronValidateError("validation error") from e
        except GRPCError as e:
            log.error("failed to complete oauth flow with hharon service", err=e)
            raise HHaronGRPCError.from_grpc(e) from e
        except Exception as e:
            log.error("failed to complete oauth flow with hharon service", err=e)
            raise HHaronError("failed to complete oauth flow") from e

    @span(op="hharon_adapter", name="get_user")
    @override
    async def get_user(self, request: HHaronProtocol.GetUserRequest) -> HHaronProtocol.GetUserResponse:
        grpc_request = GetUserRequest(user_id=str(request.user_id))

        try:
            grpc_response = await self._stub.get_user(grpc_request)

            if not grpc_response.user_id:
                raise HHaronError("hharon service returned empty user_id")

            return HHaronProtocol.GetUserResponse(
                user_id=UserID(grpc_response.user_id),
                hh_id=grpc_response.hh_manager_id,
                name=grpc_response.name,
                email=grpc_response.email,
            )
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise HHaronValidateError("validation error") from e
        except GRPCError as e:
            log.error("failed to get user from hharon service", err=e)
            raise HHaronGRPCError.from_grpc(e) from e
        except Exception as e:
            log.error("failed to get user from hharon service", err=e)
            raise HHaronError("failed to get user") from e
