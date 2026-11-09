from typing import final, override

import pydantic
import structlog
from grpclib.client import Channel
from grpclib.exceptions import GRPCError

import nanimai_platform.external_clients.casino.casino_api as casino_api
from nanimai_platform.domain import UserID
from nanimai_platform.protocols.external.balance import (
    BalanceError,
    BalanceProtocol,
    BalanceProtocolCurrency,
    BalanceValidateError,
)
from nanimai_platform.protocols.external.balance.protocol import (
    BalanceGRPCError,
    BalanceTransactionError,
    ResourceOperationType,
)
from nanimai_platform.utils.logging_span import span

_GRPC_TO_DOMAIN_CURRENCY = {
    casino_api.Currency.UNSPECIFIED: None,
    casino_api.Currency.TOKEN: BalanceProtocolCurrency.TOKEN,
    casino_api.Currency.SCORING: BalanceProtocolCurrency.SCORING,
    casino_api.Currency.DIALOG: BalanceProtocolCurrency.DIALOG,
}
_DOMAIN_TO_GRPC_CURRENCY = {v: k for k, v in _GRPC_TO_DOMAIN_CURRENCY.items()}

log = structlog.stdlib.get_logger("app.adapters.GRPCBalanceAdapter")


@final
class GRPCBalanceAdapter(BalanceProtocol):
    def __init__(self, host: str, port: int):
        self._channel = Channel(host, port)
        self._stub = casino_api.BalanceServiceStub(self._channel)

    async def close(self):
        self._channel.close()

    @span(op="grpc_balance_adapter", name="create_balance")
    @override
    async def create_balance(self, request: BalanceProtocol.CreateBalanceRequest) -> BalanceProtocol.BalanceResponse:
        try:
            grpc_req = casino_api.CreateBalanceRequest(
                user_id=str(request.user_id),
                currency=_DOMAIN_TO_GRPC_CURRENCY[request.currency],
                maximum=request.maximum,
            )

            grpc_resp = await self._stub.create_balance(grpc_req)

            if (currency := _GRPC_TO_DOMAIN_CURRENCY.get(grpc_resp.currency)) is None:
                raise BalanceValidateError("Currency is unspecified")

            return BalanceProtocol.BalanceResponse(
                balance_id=grpc_resp.balance_id,
                user_id=UserID(grpc_resp.user_id),
                currency=currency,
                current=grpc_resp.current,
                maximum=grpc_resp.maximum,
                reserved=grpc_resp.reserved,
            )
        except GRPCError as e:
            log.error("failed to create balance by grpc", err=e)
            raise BalanceGRPCError.from_grpc(e) from e
        except BalanceValidateError as e:
            log.error("failed with validation error", err=e)
            raise e
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise BalanceValidateError("validation error") from e
        except Exception as e:
            log.error("failed to create balance", err=e)
            raise BalanceError("Unexpected error") from e

    @span(op="grpc_balance_adapter", name="get_balance")
    @override
    async def get_balance(self, request: BalanceProtocol.GetBalanceRequest) -> BalanceProtocol.BalanceResponse:
        try:
            grpc_req = casino_api.GetBalanceRequest(
                user_id=str(request.user_id),
                currency=_DOMAIN_TO_GRPC_CURRENCY.get(request.currency) if request.currency is not None else None,
            )

            grpc_resp = await self._stub.get_balance(grpc_req)

            if (currency := _GRPC_TO_DOMAIN_CURRENCY.get(grpc_resp.currency)) is None:
                raise BalanceValidateError("Currency is unspecified")

            return BalanceProtocol.BalanceResponse(
                balance_id=grpc_resp.balance_id,
                user_id=UserID(grpc_resp.user_id),
                currency=currency,
                current=grpc_resp.current,
                maximum=grpc_resp.maximum,
                reserved=grpc_resp.reserved,
            )
        except GRPCError as e:
            log.error("failed to get balance by grpc", err=e)
            raise BalanceGRPCError.from_grpc(e) from e
        except BalanceValidateError as e:
            log.error("failed with validation error", err=e)
            raise e
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise BalanceValidateError("validation error") from e
        except Exception as e:
            log.error("failed to get balance", err=e)
            raise BalanceError("Unexpected error") from e

    @span(op="grpc_balance_adapter", name="create_limit")
    @override
    async def create_limit(self, request: BalanceProtocol.CreateLimitRequest) -> BalanceProtocol.LimitResponse:
        try:
            grpc_req = casino_api.CreateLimitRequest(
                balance_id=request.balance_id,
                resource_id=request.resource_id,
                maximum=request.maximum,
                currency=_DOMAIN_TO_GRPC_CURRENCY.get(request.currency) if request.currency is not None else None,
            )

            grpc_resp = await self._stub.create_limit(grpc_req)

            if (currency := _GRPC_TO_DOMAIN_CURRENCY.get(grpc_resp.currency)) is None:
                raise BalanceValidateError("Currency is unspecified")

            return BalanceProtocol.LimitResponse(
                limit_id=grpc_resp.limit_id,
                balance_id=grpc_resp.balance_id,
                resource_id=grpc_resp.resource_id,
                current=grpc_resp.current,
                maximum=grpc_resp.maximum,
                currency=currency,
            )
        except GRPCError as e:
            log.error("failed to create limit by grpc", err=e)
            raise BalanceGRPCError.from_grpc(e) from e
        except BalanceValidateError as e:
            log.error("failed with validation error", err=e)
            raise e
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise BalanceValidateError("validation error") from e
        except Exception as e:
            log.error("failed to create limit", err=e)
            raise BalanceError("Unexpected error") from e

    @span(op="grpc_balance_adapter", name="get_limit")
    @override
    async def get_limit(self, request: BalanceProtocol.GetLimitRequest) -> BalanceProtocol.GetLimitResponse:
        try:
            grpc_req = casino_api.GetLimitsRequest(
                balance_id=request.balance_id,
                currency=_DOMAIN_TO_GRPC_CURRENCY.get(request.currency) if request.currency is not None else None,
            )

            grpc_resp = await self._stub.get_limits(grpc_req)

            limits: list[BalanceProtocol.LimitResponse] = []
            for limit in grpc_resp.limits:
                if (currency := _GRPC_TO_DOMAIN_CURRENCY.get(limit.currency)) is None:
                    raise BalanceValidateError("Currency is unspecified")

                limits.append(
                    BalanceProtocol.LimitResponse(
                        limit_id=limit.limit_id,
                        balance_id=limit.balance_id,
                        resource_id=limit.resource_id,
                        current=limit.current,
                        maximum=limit.maximum,
                        currency=currency,
                    )
                )

            return BalanceProtocol.GetLimitResponse(limits=limits)
        except GRPCError as e:
            log.error("failed to get limit by grpc", err=e)
            raise BalanceGRPCError.from_grpc(e) from e
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise BalanceValidateError("validation error") from e
        except Exception as e:
            log.error("failed to get limit", err=e)
            raise BalanceError("Unexpected error") from e

    @span(op="grpc_balance_adapter", name="update_limit")
    @override
    async def update_limit(self, request: BalanceProtocol.UpdateLimitRequest) -> BalanceProtocol.LimitResponse:
        try:
            grpc_req = casino_api.UpdateLimitRequest(
                balance_id=request.balance_id,
                resource_id=request.resource_id,
                maximum=request.maximum,
            )

            grpc_resp = await self._stub.update_limit(grpc_req)

            if (currency := _GRPC_TO_DOMAIN_CURRENCY.get(grpc_resp.currency)) is None:
                raise BalanceValidateError("Currency is unspecified")

            return BalanceProtocol.LimitResponse(
                limit_id=grpc_resp.limit_id,
                balance_id=grpc_resp.balance_id,
                resource_id=grpc_resp.resource_id,
                current=grpc_resp.current,
                maximum=grpc_resp.maximum,
                currency=currency,
            )
        except GRPCError as e:
            log.error("failed to update limit by grpc", err=e)
            raise BalanceGRPCError.from_grpc(e) from e
        except BalanceValidateError as e:
            log.error("failed with validation error", err=e)
            raise e
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise BalanceValidateError("validation error") from e
        except Exception as e:
            log.error("failed to update limit", err=e)
            raise BalanceError("Unexpected error") from e

    @span(op="grpc_balance_adapter", name="upsert_limit")
    @override
    async def upsert_limit(self, request: BalanceProtocol.UpsertLimitRequest) -> BalanceProtocol.LimitResponse:
        try:
            grpc_req = casino_api.UpsertLimitRequest(
                balance_id=request.balance_id,
                resource_id=request.resource_id,
                maximum=request.maximum,
                currency=_DOMAIN_TO_GRPC_CURRENCY.get(request.currency) if request.currency is not None else None,
            )

            grpc_resp = await self._stub.upsert_limit(grpc_req)

            if (currency := _GRPC_TO_DOMAIN_CURRENCY.get(grpc_resp.currency)) is None:
                raise BalanceValidateError("Currency is unspecified")

            return BalanceProtocol.LimitResponse(
                limit_id=grpc_resp.limit_id,
                balance_id=grpc_resp.balance_id,
                resource_id=grpc_resp.resource_id,
                current=grpc_resp.current,
                maximum=grpc_resp.maximum,
                currency=currency,
            )
        except GRPCError as e:
            log.error("failed to upsert limit by grpc", err=e)
            raise BalanceGRPCError.from_grpc(e) from e
        except BalanceValidateError as e:
            log.error("failed with validation error", err=e)
            raise e
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise BalanceValidateError("validation error") from e
        except Exception as e:
            log.error("failed to upsert limit", err=e)
            raise BalanceError("Unexpected error") from e

    @span(op="grpc_balance_adapter", name="reserve_resources")
    @override
    async def reserve_resources(
        self, request: BalanceProtocol.ReserveResourcesRequest
    ) -> BalanceProtocol.ReserveResourcesResponse:
        try:
            if request.operation == ResourceOperationType.RESUME_SCORING:
                flow = casino_api.Flow.FULL_RESUME_SCORING
            else:
                raise BalanceValidateError("Invalid operation")

            grpc_request = casino_api.TriggerFlowRequest(
                user_id=request.user_id,
                flow=flow,
                resource_id=request.resource_id,
                timeout_milliseconds=int(request.timeout.total_seconds() * 1000),
            )

            response = await self._stub.trigger_flow(grpc_request)

            if response.status != casino_api.TransactionStatus.PENDING:
                raise BalanceTransactionError(f"transaction was not openned, actual status: {response.status}")

            return BalanceProtocol.ReserveResourcesResponse(reservation_id=response.transaction_id)
        except BalanceError as e:
            log.error("failed to reserver resources due to business rules", err=e)
            raise e
        except GRPCError as e:
            log.error("failed to reserve resources", err=e)
            raise BalanceGRPCError.from_grpc(e) from e
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise BalanceValidateError("validation error") from e
        except Exception as e:
            log.error("failed to reserver resources", err=e)
            raise BalanceError("Unexpected error") from e

    @span(op="grpc_balance_adapter", name="confirm_reservation")
    @override
    async def confirm_reservation(self, request: BalanceProtocol.ConfirmReservationRequest) -> None:
        try:
            grpc_request = casino_api.ConfirmFlowRequest(transaction_id=request.reservation_id)

            response = await self._stub.confirm_flow(grpc_request)

            if response.status != casino_api.TransactionStatus.CONFIRMED:
                raise BalanceError(f"transaction was not confirmed, actual status is {response.status}")

            return
        except BalanceError as e:
            log.error("transaction confirmation failed due to business rules", err=e)
            raise e from e
        except GRPCError as e:
            log.error("failed to confirm reservation", err=e)
            raise BalanceGRPCError.from_grpc(e) from e
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise BalanceValidateError("validation error") from e
        except Exception as e:
            log.error("failed to confirm reservation", err=e)
            raise BalanceError("Unexpected error") from e

    @span(op="grpc_balance_adapter", name="cancel_reservation")
    @override
    async def cancel_reservation(self, request: BalanceProtocol.CancelReservationRequest) -> None:
        try:
            grpc_request = casino_api.CancelFlowRequest(transaction_id=request.reservation_id)

            response = await self._stub.cancel_flow(grpc_request)

            if response.status != casino_api.TransactionStatus.CANCELLED:
                raise BalanceTransactionError(f"transaction was not cancelled, actual status is {response.status}")

            return
        except BalanceError as e:
            log.error("transaction cancellation failed due to business rules", err=e)
            raise e from e
        except GRPCError as e:
            log.error("failed to cancel reservation", err=e)
            raise BalanceGRPCError.from_grpc(e) from e
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise BalanceValidateError("validation error") from e
        except Exception as e:
            log.error("failed to cancel reservation", err=e)
            raise BalanceError("Unexpected error") from e
