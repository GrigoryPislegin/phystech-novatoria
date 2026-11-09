from typing import final

import pydantic
import structlog

from hharon.protocols import oauth2 as oauth2_protocol
from hharon.usecases.oauth2.state import EncryptOAuthState, EncryptOAuthStateEncryptError

log = structlog.stdlib.get_logger("hharon.usecases.oauth2.flow.InitOAuthFlow")


class InitOAuthFlowError(Exception):
    """Base exception class for InitOAuthFlow errors."""


class InitOAuthFlowAPIError(InitOAuthFlowError):
    """API error raised by InitOAuthFlow."""


@final
class InitOAuthFlow:
    def __init__(
        self,
        *,
        hh_oauth2_adapter: oauth2_protocol.OAuth2Protocol,
        encrypt_state_usecase: EncryptOAuthState,
    ) -> None:
        self._hh_oauth2_adapter = hh_oauth2_adapter
        self._encrypt_state_usecase = encrypt_state_usecase

    class InitOAuthFlowRequest(pydantic.BaseModel):
        user_id: str
        redirect_url: str

    class InitOAuthFlowResponse(pydantic.BaseModel):
        redirect_url: str

    async def init_oauth_flow(self, request: InitOAuthFlowRequest) -> InitOAuthFlowResponse:
        try:
            # 1. Encrypt state with user_id
            encrypted_state = self._encrypt_state_usecase.encrypt_oauth_state(
                EncryptOAuthState.EncryptOAuthStateRequest(
                    user_id=request.user_id,
                )
            )

            # 2. Pass redirect_url through adapter (URL is generated in platform)
            oauth_link = self._hh_oauth2_adapter.generate_oauth_link(
                oauth2_protocol.OAuth2Protocol.GenerateOAuthLinkRequest(
                    state=encrypted_state.state,
                    redirect_url=request.redirect_url,
                )
            )

            return self.InitOAuthFlowResponse(redirect_url=oauth_link.redirect_url)
        except EncryptOAuthStateEncryptError as e:
            log.exception("failed to encrypt oauth state")
            raise InitOAuthFlowError("failed to encrypt state") from e
        except oauth2_protocol.OAuth2APIError as e:
            log.exception("failed to generate oauth link via API")
            raise InitOAuthFlowAPIError("failed to generate oauth link") from e
        except oauth2_protocol.OAuth2Error as e:
            log.exception("failed to generate oauth link")
            raise InitOAuthFlowAPIError("failed to generate oauth link") from e
        except Exception as e:
            log.exception("unexpected error in init oauth flow")
            raise InitOAuthFlowError("unexpected error") from e
