from abc import ABC, abstractmethod
from datetime import timedelta
from enum import StrEnum

from pydantic import BaseModel, NonNegativeInt

from nanimai_platform.domain import UserID
from nanimai_platform.utils.map_grpc_error import AdvancedGRPCError


class BalanceError(Exception): ...


class BalanceValidateError(Exception): ...


class BalanceTransactionError(BalanceError): ...


class BalanceGRPCError(AdvancedGRPCError): ...


class BalanceProtocolCurrency(StrEnum):
    TOKEN = "TOKEN"
    SCORING = "SCORING"
    DIALOG = "DIALOG"


class ResourceOperationType(StrEnum):
    RESUME_SCORING = "RESUME_SCORING"


class BalanceProtocol(ABC):
    class CreateBalanceRequest(BaseModel):
        user_id: UserID
        currency: BalanceProtocolCurrency
        maximum: NonNegativeInt

    class BalanceResponse(BaseModel):
        balance_id: str
        user_id: UserID
        currency: BalanceProtocolCurrency
        current: NonNegativeInt
        maximum: NonNegativeInt
        reserved: NonNegativeInt

    @abstractmethod
    async def create_balance(self, request: CreateBalanceRequest) -> BalanceResponse:
        """Creates user's balance.

        Raises:
            BalanceValidationError - wrong data error
            BalanceError - unexpected error
            BalanceGRPCError - GRPC error
        Returns:
            BalanceResponse - user's balance
        """

    class GetBalanceRequest(BaseModel):
        user_id: UserID
        currency: BalanceProtocolCurrency | None = None

    @abstractmethod
    async def get_balance(self, request: GetBalanceRequest) -> BalanceResponse:
        """Get user's balance.

        Raises:
            BalanceValidationError - wrong data error
            BalanceError - unexpected error
            BalanceGRPCError - GRPC error
        Returns:
            BalanceResponse - user's balance
        """
        ...

    class CreateLimitRequest(BaseModel):
        balance_id: str
        resource_id: str
        maximum: NonNegativeInt
        currency: BalanceProtocolCurrency | None = None

    class LimitResponse(BaseModel):
        limit_id: str
        balance_id: str
        resource_id: str
        currency: BalanceProtocolCurrency
        current: NonNegativeInt
        maximum: NonNegativeInt

    @abstractmethod
    async def create_limit(self, request: CreateLimitRequest) -> LimitResponse:
        """Create limit.

        Raises:
            BalanceValidationError - wrong data error
            BalanceError - unexpected error
            BalanceGRPCError - GRPC error
        Returns:
            LimitResponse - created limit
        """
        ...

    class GetLimitRequest(BaseModel):
        balance_id: str
        currency: BalanceProtocolCurrency | None = None

    class GetLimitResponse(BaseModel):
        limits: list["BalanceProtocol.LimitResponse"]

    @abstractmethod
    async def get_limit(self, request: GetLimitRequest) -> GetLimitResponse:
        """Get limit information by balance.

        Raises:
            BalanceValidationError - wrong data error
            BalanceError - unexpected error
            BalanceGRPCError - GRPC error
        Returns:
            GetLimitResponse - list of LimitResponse
        """
        ...

    class UpdateLimitRequest(BaseModel):
        balance_id: str
        resource_id: str
        maximum: NonNegativeInt | None

    @abstractmethod
    async def update_limit(self, request: UpdateLimitRequest) -> LimitResponse:
        """Update limit.

        Raises:
            BalanceValidationError - wrong data error
            BalanceError - unexpected error
            BalanceGRPCError - GRPC error
        Returns:
            LimitResponse - updated limit
        """
        ...

    class UpsertLimitRequest(BaseModel):
        balance_id: str
        resource_id: str
        maximum: NonNegativeInt
        currency: BalanceProtocolCurrency | None = None

    @abstractmethod
    async def upsert_limit(self, request: UpsertLimitRequest) -> LimitResponse:
        """Upsert limit.

        Raises:
            BalanceValidationError - wrong data error
            BalanceError - unexpected error
            BalanceGRPCError - GRPC error
        Returns:
            LimitResponse - updated limit
        """
        ...

    class ReserveResourcesRequest(BaseModel):
        user_id: str
        resource_id: str
        operation: ResourceOperationType
        timeout: timedelta

    class ReserveResourcesResponse(BaseModel):
        reservation_id: str

    @abstractmethod
    async def reserve_resources(self, request: ReserveResourcesRequest) -> ReserveResourcesResponse: ...

    class CancelReservationRequest(BaseModel):
        reservation_id: str

    @abstractmethod
    async def cancel_reservation(self, request: CancelReservationRequest) -> None: ...

    class ConfirmReservationRequest(BaseModel):
        reservation_id: str

    @abstractmethod
    async def confirm_reservation(self, request: ConfirmReservationRequest) -> None: ...

    # async def credit()
    # async def debit()
    # async def get_operations()
    # async def trigger_flow()
    # async def confirm_flow()
    # async def cancel_flow()
    # async def process_tariff()
