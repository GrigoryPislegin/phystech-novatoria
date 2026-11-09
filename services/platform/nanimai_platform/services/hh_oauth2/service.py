from typing import final

import pydantic
import structlog

from nanimai_platform.domain import UserID
from nanimai_platform.infra.config import HHaronOAuthConfig
from nanimai_platform.protocols.external.hharon import (
    HHaronError,
    HHaronGRPCError,
    HHaronProtocol,
    HHaronValidateError,
)
from nanimai_platform.services.user_profile import (
    UserService,
    UserServiceError,
    UserServiceInvalidDataError,
    UserServiceUserNotFoundError,
)
from nanimai_platform.utils.logging_span import span
from nanimai_platform.utils.map_grpc_error import AdvancedGRPCError

log = structlog.stdlib.get_logger("app.service.HHOAuth2Service")


class HHOAuth2ServiceError(Exception): ...


class HHOAuth2ServiceInvalidDataError(HHOAuth2ServiceError): ...


class HHOAuth2ServiceHHaronGRPCError(AdvancedGRPCError): ...


class HHOAuth2ServiceUserNotFoundError(HHOAuth2ServiceError): ...


@final
class HHOAuth2Service:
    def __init__(
        self,
        hharon_adapter: HHaronProtocol,
        user_service: UserService,
        cfg: HHaronOAuthConfig,
    ):
        self._hharon_adapter = hharon_adapter
        self._user_service = user_service
        self._platform_after_auth_url = cfg.platform_after_auth_url
        self._final_redirect_back_url = cfg.final_redirect_back_url

    class InitOAuthFlowRequest(pydantic.BaseModel):
        user_id: UserID

    class InitOAuthFlowResponse(pydantic.BaseModel):
        redirect_url: str

    @span(op="hh_oauth2_service", name="init_oauth_flow")
    async def init_oauth_flow(self, request: InitOAuthFlowRequest) -> InitOAuthFlowResponse:
        try:
            response = await self._hharon_adapter.init_oauth_flow(
                HHaronProtocol.InitOAuthFlowRequest(
                    user_id=str(request.user_id),
                    redirect_url=self._platform_after_auth_url,
                )
            )

            return self.InitOAuthFlowResponse(redirect_url=response.redirect_url)

        except HHaronValidateError as e:
            log.error("Failed to init oauth flow due to validation error", err=e)
            raise HHOAuth2ServiceInvalidDataError("invalid data") from e
        except HHaronGRPCError as e:
            log.error("Failed to init oauth flow due to GRPC error", err=e)
            raise HHOAuth2ServiceHHaronGRPCError.from_adv(e) from e
        except HHaronError as e:
            log.error("Failed to init oauth flow due to HHaron error", err=e)
            raise HHOAuth2ServiceError("Failed to init oauth flow") from e
        except Exception as e:
            log.exception("Failed to init oauth flow", err=e)
            raise HHOAuth2ServiceError("Unexpected error") from e

    class CompleteOAuthFlowRequest(pydantic.BaseModel):
        secret_code: str | None
        state: str
        error: str | None

    class CompleteOAuthFlowResponse(pydantic.BaseModel):
        redirect_back: str
        message: str | None = None

    @span(op="hh_oauth2_service", name="complete_oauth_flow")
    async def complete_oauth_flow(self, request: CompleteOAuthFlowRequest) -> CompleteOAuthFlowResponse:
        try:
            return await self.__complete_oauth_flow_helper(request)
        except Exception:
            return self.CompleteOAuthFlowResponse(
                redirect_back=self._final_redirect_back_url,
                message="Не удалось подключить аккаунт к Headhunter",
            )

    @span(op="hh_oauth2_service", name="complete_oauth_flow")
    async def __complete_oauth_flow_helper(self, request: CompleteOAuthFlowRequest) -> CompleteOAuthFlowResponse:
        try:
            if request.secret_code is None or request.error is not None:
                raise HHOAuth2ServiceInvalidDataError("either missing secret_code or error is present")

            response = await self._hharon_adapter.complete_oauth_flow(
                HHaronProtocol.CompleteOAuthFlowRequest(
                    secret_code=request.secret_code,
                    encrypted_state=request.state,
                    redirect_uri=self._platform_after_auth_url,
                )
            )

            if not response.success:
                log.warning("OAuth flow was not successful")
                raise HHOAuth2ServiceError("OAuth flow failed")

            return self.CompleteOAuthFlowResponse(redirect_back=self._final_redirect_back_url)
        except (HHaronValidateError, UserServiceInvalidDataError) as e:
            log.error("Failed to complete oauth flow due to validation error", err=e)
            raise HHOAuth2ServiceInvalidDataError("invalid data") from e
        except HHaronGRPCError as e:
            log.error("Failed to complete oauth flow due to GRPC error", err=e)
            raise HHOAuth2ServiceHHaronGRPCError.from_adv(e) from e
        except HHaronError as e:
            log.error("Failed to complete oauth flow due to HHaron error", err=e)
            raise HHOAuth2ServiceError("Failed to complete oauth flow") from e
        except UserServiceUserNotFoundError as e:
            log.error("Failed to complete oauth flow due to user service user not found error", err=e)
            raise HHOAuth2ServiceUserNotFoundError("Failed to update user") from e
        except UserServiceError as e:
            log.error("Failed to complete oauth flow due to user service error", err=e)
            raise HHOAuth2ServiceError("Failed to update user") from e
        except Exception as e:
            log.exception("Failed to complete oauth flow", err=e)
            raise HHOAuth2ServiceError("Unexpected error") from e
