from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from nanimai_platform.domain.user_profile.user_profile import UserID
from nanimai_platform.utils.map_grpc_error import AdvancedGRPCError


class HHaronError(Exception): ...


class HHaronValidateError(Exception): ...


class HHaronGRPCError(AdvancedGRPCError): ...


class HHaronProtocol(ABC):
    class InitOAuthFlowRequest(BaseModel):
        user_id: str
        redirect_url: str

    class InitOAuthFlowResponse(BaseModel):
        redirect_url: str

    @abstractmethod
    async def init_oauth_flow(self, request: InitOAuthFlowRequest) -> InitOAuthFlowResponse:
        """Initiates OAuth flow for user authentication.

        Args:
            request: InitOAuthFlowRequest containing user_id and redirect_url

        Raises:
            HHaronValidateError - wrong data error
            HHaronError - unexpected error
            HHaronGRPCError - GRPC error

        Returns:
            InitOAuthFlowResponse - redirect URL for OAuth flow
        """
        ...

    class CompleteOAuthFlowRequest(BaseModel):
        secret_code: str
        encrypted_state: str
        redirect_uri: str

    class CompleteOAuthFlowResponse(BaseModel):
        user_id: UserID
        success: bool

    @abstractmethod
    async def complete_oauth_flow(self, request: CompleteOAuthFlowRequest) -> CompleteOAuthFlowResponse:
        """Completes OAuth flow and returns Hharon user ID.

        Args:
            request: CompleteOAuthFlowRequest with secret_code, encrypted_state, and redirect_uri

        Raises:
            HHaronValidateError - wrong data error
            HHaronError - unexpected error
            HHaronGRPCError - GRPC error

        Returns:
            CompleteOAuthFlowResponse - success status and hharon_id
        """
        ...

    class GetUserRequest(BaseModel):
        user_id: UserID

    class GetUserResponse(BaseModel):
        user_id: UserID
        hh_id: str
        name: str
        email: str

    @abstractmethod
    async def get_user(self, request: GetUserRequest) -> GetUserResponse:
        """Retrieves user information by Hharon ID.

        Args:
            request: GetUserRequest containing hharon_id

        Raises:
            HHaronValidateError - wrong data error
            HHaronError - unexpected error
            HHaronGRPCError - GRPC error

        Returns:
            GetUserResponse - user information including hh_id, name, and email
        """
        ...
