from __future__ import annotations

from datetime import timedelta
from typing import final

import structlog
from pydantic import BaseModel, NonNegativeInt

from nanimai_platform.domain import UserID, VacancyID
from nanimai_platform.protocols.external.balance import (
    BalanceError,
    BalanceGRPCError,
    BalanceProtocol,
    BalanceProtocolCurrency,
    BalanceValidateError,
)
from nanimai_platform.services.cache.cache import Cache
from nanimai_platform.services.cache.keyspace import Key, Keyspace
from nanimai_platform.utils.asyncio_background import launch_background
from nanimai_platform.utils.logging_span import span
from nanimai_platform.utils.map_grpc_error import AdvancedGRPCError

log = structlog.stdlib.get_logger("app.service.BalanceService")


class BalanceServiceError(Exception): ...


class BalanceServiceInvalidDataError(BalanceServiceError): ...


class BalanceServiceBalanceGRPCError(AdvancedGRPCError): ...


@final
class BalanceService:
    def __init__(
        self,
        cache: Cache,
        balance_adapter: BalanceProtocol,
    ):
        self._cache = cache
        self._ks = Keyspace("balance_service")
        self._balance_adapter = balance_adapter

    class CreateTokenBalanceRequest(BaseModel):
        user_id: UserID
        maximum: NonNegativeInt

    class GetBalanceIdRequest(BaseModel):
        user_id: UserID

    class BalanceResponse(BaseModel):
        balance_id: str
        user_id: UserID
        currency: BalanceProtocolCurrency
        current: NonNegativeInt
        maximum: NonNegativeInt
        reserved: NonNegativeInt

    @span(op="balance_service", name="create_balance")
    async def create_token_balance(self, request: CreateTokenBalanceRequest) -> BalanceResponse:
        try:
            response = await self._balance_adapter.create_balance(
                BalanceProtocol.CreateBalanceRequest(
                    user_id=request.user_id,
                    currency=BalanceProtocolCurrency.TOKEN,
                    maximum=request.maximum,
                )
            )

            balance_response = self.BalanceResponse(
                balance_id=response.balance_id,
                user_id=response.user_id,
                current=response.current,
                maximum=response.maximum,
                reserved=response.reserved,
                currency=response.currency,
            )

            # Cache the balance_id for 1 day in background
            @launch_background
            async def update_cache():
                await self._cache.set(
                    self._user_balance_id_key(request.user_id),
                    {"balance_id": response.balance_id},
                    expire=timedelta(days=1),
                )

            update_cache()

            return balance_response
        except BalanceGRPCError as e:
            log.error("failed to create balance due to grpc error", err=e)
            raise BalanceServiceBalanceGRPCError.from_adv(e) from e
        except BalanceValidateError as e:
            log.error("failed to create balance due to validation error", err=e)
            raise BalanceServiceInvalidDataError("invalid data") from e
        except BalanceError as e:
            log.error("failed to create balance", err=e)
            raise BalanceServiceError("failed to create balance") from e
        except Exception as e:
            log.error("failed to create balance", err=e)
            raise BalanceServiceError("unknown error") from e

    class GetBalanceRequest(BaseModel):
        user_id: UserID

    @span(op="balance_service", name="get_balance_id")
    async def get_balance_id(self, request: GetBalanceIdRequest) -> str:
        try:
            # Try to get cached balance_id first
            cached_balance_id = await self._cache.get(self._user_balance_id_key(request.user_id))
            if cached_balance_id is not None:
                return cached_balance_id["balance_id"]

            # If not in cache, fetch from adapter
            response = await self._balance_adapter.get_balance(
                BalanceProtocol.GetBalanceRequest(user_id=request.user_id)
            )

            # Cache only the balance_id for 1 day in background
            @launch_background
            async def update_cache():
                await self._cache.set(
                    self._user_balance_id_key(request.user_id),
                    {"balance_id": response.balance_id},
                    expire=timedelta(days=1),
                )

            update_cache()

            return response.balance_id
        except BalanceGRPCError as e:
            log.error("failed to get balance_id due to grpc error", err=e)
            raise BalanceServiceBalanceGRPCError.from_adv(e) from e
        except BalanceValidateError as e:
            log.error("failed to get balance_id due to validation error", err=e)
            raise BalanceServiceInvalidDataError("invalid data") from e
        except BalanceError as e:
            log.error("failed to get balance_id", err=e)
            raise BalanceServiceError("failed to get balance_id") from e
        except Exception as e:
            log.error("failed to get balance_id", err=e)
            raise BalanceServiceError("unknown error") from e

    @span(op="balance_service", name="get_balance")
    async def get_balance(self, request: GetBalanceRequest) -> BalanceResponse:
        try:
            # Always fetch full balance from adapter (not cached)
            response = await self._balance_adapter.get_balance(
                BalanceProtocol.GetBalanceRequest(
                    user_id=request.user_id,
                    currency=BalanceProtocolCurrency.TOKEN,
                )
            )

            balance_response = self.BalanceResponse(
                balance_id=response.balance_id,
                user_id=response.user_id,
                current=response.current,
                maximum=response.maximum,
                reserved=response.reserved,
                currency=response.currency,
            )

            # Update balance_id cache in background (balance_id might have changed)
            @launch_background
            async def update_cache():
                await self._cache.set(
                    self._user_balance_id_key(request.user_id),
                    {"balance_id": response.balance_id},
                    expire=timedelta(days=1),
                )

            update_cache()

            return balance_response
        except BalanceGRPCError as e:
            log.error("failed to get balance due to grpc error", err=e)
            raise BalanceServiceBalanceGRPCError.from_adv(e) from e
        except BalanceValidateError as e:
            log.error("failed to get balance due to validation error", err=e)
            raise BalanceServiceInvalidDataError("invalid data") from e
        except BalanceError as e:
            log.error("failed to get balance", err=e)
            raise BalanceServiceError("failed to get balance") from e
        except Exception as e:
            log.error("failed to get balance", err=e)
            raise BalanceServiceError("unknown error") from e

    class CreateLimitRequest(BaseModel):
        user_id: UserID
        resource_id: VacancyID
        maximum: NonNegativeInt

    class LimitResponse(BaseModel):
        limit_id: str
        balance_id: str
        resource_id: str
        currency: BalanceProtocolCurrency
        current: NonNegativeInt
        maximum: NonNegativeInt

    @span(op="balance_service", name="create_limit")
    async def create_limit(self, request: CreateLimitRequest) -> LimitResponse:
        try:
            balance_id = await self.get_balance_id(self.GetBalanceIdRequest(user_id=request.user_id))

            response = await self._balance_adapter.create_limit(
                BalanceProtocol.CreateLimitRequest(
                    balance_id=balance_id,
                    resource_id=str(request.resource_id),
                    maximum=request.maximum,
                    currency=BalanceProtocolCurrency.SCORING,
                )
            )
            return self.LimitResponse(
                limit_id=response.limit_id,
                balance_id=response.balance_id,
                resource_id=response.resource_id,
                currency=response.currency,
                current=response.current,
                maximum=response.maximum,
            )
        except BalanceServiceBalanceGRPCError as e:
            raise e
        except BalanceGRPCError as e:
            log.error("failed to create limit due to grpc error", err=e)
            raise BalanceServiceBalanceGRPCError.from_adv(e) from e
        except BalanceValidateError as e:
            log.error("failed to create limit due to validation error", err=e)
            raise BalanceServiceInvalidDataError("invalid data") from e
        except BalanceError as e:
            log.error("failed to create limit", err=e)
            raise BalanceServiceError("failed to create limit") from e
        except Exception as e:
            log.error("failed to create limit", err=e)
            raise BalanceServiceError("unknown error") from e

    class GetLimitRequest(BaseModel):
        balance_id: str

    class GetLimitResponse(BaseModel):
        limits: list[BalanceService.LimitResponse]

    @span(op="balance_service", name="get_limit")
    async def get_limit(self, request: GetLimitRequest) -> GetLimitResponse:
        try:
            response = await self._balance_adapter.get_limit(
                BalanceProtocol.GetLimitRequest(
                    balance_id=request.balance_id,
                    currency=BalanceProtocolCurrency.SCORING,
                )
            )
            limits = [
                self.LimitResponse(
                    limit_id=limit.limit_id,
                    balance_id=limit.balance_id,
                    resource_id=limit.resource_id,
                    currency=limit.currency,
                    current=limit.current,
                    maximum=limit.maximum,
                )
                for limit in response.limits
            ]
            return self.GetLimitResponse(
                limits=limits,
            )
        except BalanceGRPCError as e:
            log.error("failed to get limit due to grpc error", err=e)
            raise BalanceServiceBalanceGRPCError.from_adv(e) from e
        except BalanceValidateError as e:
            log.error("failed to get limit due to validation error", err=e)
            raise BalanceServiceInvalidDataError("invalid data") from e
        except BalanceError as e:
            log.error("failed to get limit", err=e)
            raise BalanceServiceError("failed to get limit") from e
        except Exception as e:
            log.error("failed to get limit", err=e)
            raise BalanceServiceError("unknown error") from e

    class GetLimitByUserRequest(BaseModel):
        user_id: UserID

    @span(op="balance_service", name="get_limit_by_user")
    async def get_limit_by_user(self, request: GetLimitByUserRequest) -> GetLimitResponse:
        try:
            # First get the user's balance_id (cached)
            balance_id = await self.get_balance_id(self.GetBalanceIdRequest(user_id=request.user_id))

            # Then get limits using the balance_id
            return await self.get_limit(
                self.GetLimitRequest(
                    balance_id=balance_id,
                )
            )
        except BalanceServiceBalanceGRPCError as e:
            raise e
        except BalanceGRPCError as e:
            log.error("failed to get limit by user due to grpc error", err=e)
            raise BalanceServiceBalanceGRPCError.from_adv(e) from e
        except BalanceServiceInvalidDataError as e:
            log.error("failed to get limit by user due to validation error", err=e)
            raise BalanceServiceInvalidDataError("invalid data") from e
        except BalanceServiceError as e:
            log.error("failed to get limit by user", err=e)
            raise BalanceServiceError("failed to get limit by user") from e
        except Exception as e:
            log.error("failed to get limit by user", err=e)
            raise BalanceServiceError("unknown error") from e

    class GetLimitByVacancyRequest(BaseModel):
        user_id: UserID
        vacancy_id: VacancyID

    class GetSingleLimitResponse(BaseModel):
        limit_id: str | None
        balance_id: str | None
        resource_id: str | None
        currency: BalanceProtocolCurrency | None
        current: NonNegativeInt | None
        maximum: NonNegativeInt | None

    @span(op="balance_service", name="get_limit_by_vacancy")
    async def get_limit_by_vacancy(self, request: GetLimitByVacancyRequest) -> GetSingleLimitResponse:
        try:
            # First get all limits for the user
            all_limits_response = await self.get_limit_by_user(
                self.GetLimitByUserRequest(
                    user_id=request.user_id,
                )
            )

            # Find the single limit for this vacancy (resource_id)
            vacancy_limit = None
            for limit in all_limits_response.limits:
                if limit.resource_id == str(request.vacancy_id):
                    vacancy_limit = limit
                    break

            if vacancy_limit:
                return self.GetSingleLimitResponse(
                    limit_id=vacancy_limit.limit_id,
                    balance_id=vacancy_limit.balance_id,
                    resource_id=vacancy_limit.resource_id,
                    currency=vacancy_limit.currency,
                    current=vacancy_limit.current,
                    maximum=vacancy_limit.maximum,
                )
            else:
                return self.GetSingleLimitResponse(
                    limit_id=None,
                    balance_id=None,
                    resource_id=None,
                    currency=None,
                    current=None,
                    maximum=None,
                )
        except BalanceServiceBalanceGRPCError as e:
            raise e
        except BalanceGRPCError as e:
            log.error("failed to get limit by vacancy due to grpc error", err=e)
            raise BalanceServiceBalanceGRPCError.from_adv(e) from e
        except BalanceServiceInvalidDataError as e:
            log.error("failed to get limit by vacancy due to validation error", err=e)
            raise BalanceServiceInvalidDataError("invalid data") from e
        except BalanceServiceError as e:
            log.error("failed to get limit by vacancy", err=e)
            raise BalanceServiceError("failed to get limit by vacancy") from e
        except Exception as e:
            log.error("failed to get limit by vacancy", err=e)
            raise BalanceServiceError("unknown error") from e

    class UpdateLimitRequest(BaseModel):
        user_id: UserID
        resource_id: VacancyID
        maximum: NonNegativeInt | None

    @span(op="balance_service", name="update_limit")
    async def update_limit(self, request: UpdateLimitRequest) -> LimitResponse:
        try:
            balance_id = await self.get_balance_id(self.GetBalanceIdRequest(user_id=request.user_id))

            response = await self._balance_adapter.update_limit(
                BalanceProtocol.UpdateLimitRequest(
                    balance_id=balance_id,
                    resource_id=str(request.resource_id),
                    maximum=request.maximum if request.maximum else None,
                )
            )
            return self.LimitResponse(
                limit_id=response.limit_id,
                balance_id=response.balance_id,
                resource_id=response.resource_id,
                currency=response.currency,
                current=response.current,
                maximum=response.maximum,
            )
        except BalanceServiceBalanceGRPCError as e:
            raise e
        except BalanceGRPCError as e:
            log.error("failed to update limit due to grpc error", err=e)
            raise BalanceServiceBalanceGRPCError.from_adv(e) from e
        except BalanceValidateError as e:
            log.error("failed to update limit due to validation error", err=e)
            raise BalanceServiceInvalidDataError("invalid data") from e
        except BalanceError as e:
            log.error("failed to update limit", err=e)
            raise BalanceServiceError("failed to update limit") from e
        except Exception as e:
            log.error("failed to update limit", err=e)
            raise BalanceServiceError("unknown error") from e

    class UpsertLimitRequest(BaseModel):
        user_id: UserID
        resource_id: VacancyID
        maximum: NonNegativeInt

    @span(op="balance_service", name="upsert_limit")
    async def upsert_limit(self, request: UpsertLimitRequest) -> LimitResponse:
        try:
            balance_id = await self.get_balance_id(self.GetBalanceIdRequest(user_id=request.user_id))

            response = await self._balance_adapter.upsert_limit(
                BalanceProtocol.UpsertLimitRequest(
                    balance_id=balance_id,
                    resource_id=str(request.resource_id),
                    maximum=request.maximum,
                    currency=BalanceProtocolCurrency.SCORING,
                )
            )
            return self.LimitResponse(
                limit_id=response.limit_id,
                balance_id=response.balance_id,
                resource_id=response.resource_id,
                currency=response.currency,
                current=response.current,
                maximum=response.maximum,
            )
        except BalanceServiceBalanceGRPCError as e:
            raise e
        except BalanceGRPCError as e:
            log.error("failed to upsert limit due to grpc error", err=e)
            raise BalanceServiceBalanceGRPCError.from_adv(e) from e
        except BalanceValidateError as e:
            log.error("failed to upsert limit due to validation error", err=e)
            raise BalanceServiceInvalidDataError("invalid data") from e
        except BalanceError as e:
            log.error("failed to upsert limit", err=e)
            raise BalanceServiceError("failed to upsert limit") from e
        except Exception as e:
            log.error("failed to upsert limit", err=e)
            raise BalanceServiceError("unknown error") from e

    # ===

    def _user_balance_id_key(self, user_id: UserID) -> Key:
        return self._ks.key("user_balance_id", str(user_id))
