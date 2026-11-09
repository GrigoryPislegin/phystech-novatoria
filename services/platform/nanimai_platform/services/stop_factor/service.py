import asyncio
from typing import final

import structlog
from pydantic import BaseModel

from nanimai_platform.domain import ProjectID, StopFactor, StopFactorID, StopFactorPayload, UserID, VacancyID
from nanimai_platform.protocols.internal import repository as protocol
from nanimai_platform.protocols.internal.repository import StopFactorRepositoryProtocol
from nanimai_platform.services.cache.cache import Cache
from nanimai_platform.services.cache.keyspace import Key, Keyspace
from nanimai_platform.services.vacancy.service import VacancyService, VacancyServiceVacancyNotFoundError
from nanimai_platform.utils.asyncio_background import launch_background
from nanimai_platform.utils.logging_span import span

log = structlog.stdlib.get_logger("app.service.StopFactorService")


class StopFactorServiceError(Exception): ...


class StopFactorServiceInvalidDataError(Exception): ...


class StopFactorServiceStopFactorNotFoundError(Exception): ...


class StopFactorServiceVacancyNotFoundError(Exception): ...


@final
class StopFactorService:
    def __init__(
        self,
        cache: Cache,
        stop_factor_repo: StopFactorRepositoryProtocol,
        vacancy_service: VacancyService,
    ):
        self._cache = cache
        self._ks = Keyspace("stop_factor_service")
        self._stop_factor_repo = stop_factor_repo
        self._vacancy_service = vacancy_service

    class CreateStopFactorRequest(BaseModel):
        user_id: UserID
        project_id: ProjectID
        vacancy_id: VacancyID
        stop_factor: str
        initial_weight: int

    @span(op="stop_factor_service", name="create_stop_factor")
    async def create(self, request: CreateStopFactorRequest) -> StopFactor:
        try:
            stop_factor = await self._stop_factor_repo.create_stop_factor(
                StopFactorRepositoryProtocol.CreateStopFactorRequest(
                    user_id=request.user_id,
                    project_id=request.project_id,
                    vacancy_id=request.vacancy_id,
                    stop_factor=request.stop_factor,
                    initial_weight=request.initial_weight,
                )
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._stop_factor_key(stop_factor.id), stop_factor)
                await self._cache.sadd(self._vacancy_set_key(request.vacancy_id), {"id": str(stop_factor.id)})

            update_cache()

            return stop_factor

        except protocol.VacancyNotFoundError as e:
            log.error("failed to find vacancy", err=e)
            raise StopFactorServiceVacancyNotFoundError("vacancy not found") from e
        except protocol.StopFactorValidateError as e:
            log.error("failed to create stop factor due to validation error", err=e)
            raise StopFactorServiceInvalidDataError("invalid data") from e
        except protocol.CreateStopFactorError as e:
            log.error("failed to create stop factor", err=e)
            raise StopFactorServiceError("failed to create") from e
        except Exception as e:
            log.error("failed to create stop factor", err=e)
            raise StopFactorServiceError("unknown error") from e

    class CreateManyStopFactorsRequest(BaseModel):
        user_id: UserID
        project_id: ProjectID
        vacancy_id: VacancyID
        stop_factors: list[StopFactorPayload]

    @span(op="stop_factor_service", name="create_many_stop_factors")
    async def create_many(self, request: CreateManyStopFactorsRequest) -> list[StopFactorID]:
        try:
            stop_factor_ids = await self._stop_factor_repo.create_many_stop_factors(
                StopFactorRepositoryProtocol.CreateManyStopFactorsRequest(
                    user_id=request.user_id,
                    project_id=request.project_id,
                    vacancy_id=request.vacancy_id,
                    stop_factors=request.stop_factors,
                )
            )

            @launch_background
            async def update_cache():
                ids = [{"id": str(sf_id)} for sf_id in stop_factor_ids]

                await self._cache.sadd(self._vacancy_set_key(request.vacancy_id), *ids)

            update_cache()

            return stop_factor_ids

        except protocol.VacancyNotFoundError as e:
            log.error("failed to find vacancy", err=e)
            raise StopFactorServiceVacancyNotFoundError("vacancy not found") from e
        except protocol.StopFactorValidateError as e:
            log.error("failed to create stop factor due to validation error", err=e)
            raise StopFactorServiceInvalidDataError("invalid data") from e
        except protocol.CreateStopFactorError as e:
            log.error("failed to create stop factor", err=e)
            raise StopFactorServiceError("failed to create") from e
        except Exception as e:
            log.error("failed to create stop factor", err=e)
            raise StopFactorServiceError("unknown error") from e

    class ReadStopFactorRequest(BaseModel):
        id: StopFactorID

    @span(op="stop_factor_service", name="read_stop_factor")
    async def read(self, request: ReadStopFactorRequest) -> StopFactor:
        try:
            if (stop_factor := await self._cache.get(self._stop_factor_key(request.id), t=StopFactor)) is not None:
                return stop_factor

            stop_factor = await self._stop_factor_repo.read_stop_factor(
                StopFactorRepositoryProtocol.ReadStopFactorRequest(id=request.id)
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._stop_factor_key(stop_factor.id), stop_factor)
                await self._cache.sadd(self._vacancy_set_key(stop_factor.vacancy_id), {"id": str(stop_factor.id)})

            update_cache()

            return stop_factor

        except protocol.StopFactorNotFoundError as e:
            log.error("failed to find stop_factor", err=e)
            raise StopFactorServiceStopFactorNotFoundError("stop_factor not found") from e
        except protocol.StopFactorValidateError as e:
            log.error("failed to read stop_factor due to validation error", err=e)
            raise StopFactorServiceInvalidDataError("invalid data") from e
        except protocol.ReadStopFactorError as e:
            log.error("failed to read stop_factor", err=e)
            raise StopFactorServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read stop_factor", err=e)
            raise StopFactorServiceError("unknown error") from e

    class ReadManyStopFactorsRequest(BaseModel):
        stop_factor_ids: list[StopFactorID]

    @span(op="stop_factor_service", name="read_many_stop_factors")
    async def read_many(self, request: ReadManyStopFactorsRequest) -> list[StopFactor | None]:  # noqa: C901
        try:
            stop_factors = {}

            cache_stop_factors = await self._cache.mget(
                [self._stop_factor_key(sf_id) for sf_id in request.stop_factor_ids], t=StopFactor
            )

            for stop_factor in cache_stop_factors:
                if stop_factor is not None:
                    stop_factors[stop_factor.id] = stop_factor

            retrieve_from_db = list(set(request.stop_factor_ids) - set(stop_factors.keys()))

            db_stop_factors = await self._stop_factor_repo.read_many_stop_factors(
                StopFactorRepositoryProtocol.ReadManyStopFactorsRequest(stop_factor_ids=retrieve_from_db)
            )
            for stop_factor in db_stop_factors:
                if stop_factor is not None:
                    stop_factors[stop_factor.id] = stop_factor

            @launch_background
            async def update_cache():
                if stop_factors:
                    await self._cache.mset({
                        self._stop_factor_key(sf_id): stop_factor for sf_id, stop_factor in stop_factors.items()
                    })

                grouped_by_vacancy = {}
                for stop_factor in stop_factors.values():
                    if stop_factor.vacancy_id not in grouped_by_vacancy:
                        grouped_by_vacancy[stop_factor.vacancy_id] = []
                    grouped_by_vacancy[stop_factor.vacancy_id].append({"id": str(stop_factor.id)})

                await asyncio.gather(*[
                    self._cache.sadd(self._vacancy_set_key(vacancy_id), *stop_factor_ids)
                    for vacancy_id, stop_factor_ids in grouped_by_vacancy.items()
                ])

            update_cache()

            return [stop_factors.get(stop_factor_id, None) for stop_factor_id in request.stop_factor_ids]

        except protocol.StopFactorValidateError as e:
            log.error("failed to read stop factor due to validation error", err=e)
            raise StopFactorServiceInvalidDataError("invalid data") from e
        except protocol.ReadStopFactorError as e:
            log.error("failed to read stop factor", err=e)
            raise StopFactorServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read stop factor", err=e)
            raise StopFactorServiceError("unknown error") from e

    class UpdateStopFactorRequest(BaseModel):
        id: StopFactorID

        stop_factor: str | None = None
        initial_weight: int | None = None

    @span(op="stop_factor_service", name="update_stop_factor")
    async def update(self, request: UpdateStopFactorRequest) -> StopFactor:
        try:
            stop_factor = await self._stop_factor_repo.update_stop_factor(
                StopFactorRepositoryProtocol.UpdateStopFactorRequest(
                    id=request.id,
                    stop_factor=request.stop_factor,
                    initial_weight=request.initial_weight,
                )
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._stop_factor_key(stop_factor.id), stop_factor)
                await self._cache.sadd(self._vacancy_set_key(stop_factor.vacancy_id), {"id": str(stop_factor.id)})

            update_cache()

            return stop_factor

        except protocol.StopFactorNotFoundError as e:
            log.error("failed to find stop factor", err=e)
            raise StopFactorServiceStopFactorNotFoundError("stop factor not found") from e
        except protocol.StopFactorValidateError as e:
            log.error("failed to update stop factor due to validation error", err=e)
            raise StopFactorServiceInvalidDataError("invalid data") from e
        except protocol.UpdateStopFactorError as e:
            log.error("failed to update stop factor", err=e)
            raise StopFactorServiceError("failed to update") from e
        except Exception as e:
            log.error("failed to update stop factor", err=e)
            raise StopFactorServiceError("unknown error") from e

    class DeleteStopFactorRequest(BaseModel):
        id: StopFactorID

    @span(op="stop_factor_service", name="delete_stop_factor")
    async def delete(self, request: DeleteStopFactorRequest) -> StopFactor:
        try:
            stop_factor = await self._stop_factor_repo.delete_stop_factor(
                StopFactorRepositoryProtocol.DeleteStopFactorRequest(id=request.id)
            )

            await self._cache.invalidate(self._stop_factor_key(stop_factor.id))
            await self._cache.srem(self._vacancy_set_key(stop_factor.vacancy_id), {"id": str(stop_factor.id)})

            return stop_factor
        except protocol.StopFactorNotFoundError as e:
            log.error("failed to find stop factor", err=e)
            raise StopFactorServiceStopFactorNotFoundError("stop factor not found") from e
        except protocol.StopFactorValidateError as e:
            log.error("failed to delete stop factor due to validation error", err=e)
            raise StopFactorServiceInvalidDataError("invalid data") from e
        except protocol.DeleteStopFactorError as e:
            log.error("failed to delete stop factor", err=e)
            raise StopFactorServiceError("failed to delete") from e
        except Exception as e:
            log.error("failed to delete stop factor", err=e)
            raise StopFactorServiceError("unknown error") from e

    class ReadManyStopFactorsByVacancyRequest(BaseModel):
        vacancy_id: VacancyID

    @span(op="stop_factor_service", name="read_many_stop_factors_by_vacancy")
    async def read_many_by_vacancy(self, request: ReadManyStopFactorsByVacancyRequest) -> list[StopFactor]:  # noqa: C901
        try:
            stop_factors: dict[StopFactorID, StopFactor] = {}

            _ = await self._vacancy_service.read(self._vacancy_service.ReadVacancyRequest(id=request.vacancy_id))

            stop_factors_set: list[str] = [
                d["id"] for d in (await self._cache.smembers(self._vacancy_set_key(request.vacancy_id)))
            ]
            log.info("retrieved stop factors set from cache", count=len(stop_factors_set))

            if not stop_factors_set:
                db_only_stop_factors = await self._stop_factor_repo.read_many_stop_factors_by_vacancy(
                    StopFactorRepositoryProtocol.ReadManyStopFactorsByVacancyRequest(vacancy_id=request.vacancy_id)
                )
                log.info("retrieved stop factors from db", count=len(db_only_stop_factors))

                @launch_background
                async def update_cache_from_db():
                    log.info("invalidating vacancy set cache for stop factors", vacancy_id=request.vacancy_id)
                    await self._cache.invalidate(self._vacancy_set_key(request.vacancy_id))

                    if db_only_stop_factors:
                        await self._cache.mset({
                            self._stop_factor_key(stop_factor.id): stop_factor for stop_factor in db_only_stop_factors
                        })
                        await self._cache.sadd(
                            self._vacancy_set_key(request.vacancy_id),
                            *[{"id": str(stop_factor.id)} for stop_factor in db_only_stop_factors],
                        )

                update_cache_from_db()

                return db_only_stop_factors

            cache_stop_factors = await self._cache.mget(
                [self._stop_factor_key(StopFactorID(stop_factors_id)) for stop_factors_id in stop_factors_set],
                t=StopFactor,
            )
            log.info("retrieved stop factors entities from cache", count=len(cache_stop_factors))

            from_cache = 0
            for stop_factor in cache_stop_factors:
                if stop_factor is not None:
                    stop_factors[stop_factor.id] = stop_factor
                    from_cache += 1

            retrieve_from_db = list({StopFactorID(sf_id) for sf_id in stop_factors_set} - set(stop_factors.keys()))
            db_stop_factors = await self._stop_factor_repo.read_many_stop_factors(
                StopFactorRepositoryProtocol.ReadManyStopFactorsRequest(stop_factor_ids=retrieve_from_db)
            )
            log.info("retrieved stop factors from db", count=len(db_stop_factors))
            from_db = 0
            for stop_factor in db_stop_factors:
                if stop_factor is not None:
                    stop_factors[stop_factor.id] = stop_factor
                    from_db += 1

            log.info(
                "cache hit statistics: stop_factors retrieved",
                count=len(stop_factors),
                cache_hit_ratio=from_cache / len(stop_factors),
                db_hit_ratio=from_db / len(stop_factors),
            )

            @launch_background
            async def update_cache():
                log.info("invalidating vacancy set cache for stop_factors", vacancy_id=request.vacancy_id)
                await self._cache.invalidate(self._vacancy_set_key(request.vacancy_id))

                if stop_factors:
                    await self._cache.mset({
                        self._stop_factor_key(stop_factor.id): stop_factor for stop_factor in stop_factors.values()
                    })
                    await self._cache.sadd(
                        self._vacancy_set_key(request.vacancy_id),
                        *[{"id": str(stop_factor.id)} for stop_factor in stop_factors.values()],
                    )

            update_cache()

            return list(stop_factors.values())

        except VacancyServiceVacancyNotFoundError as e:
            log.error("failed to find vacancy", err=e)
            raise StopFactorServiceVacancyNotFoundError("vacancy not found") from e
        except protocol.StopFactorValidateError as e:
            log.error("failed to read many stop factors due to validation error", err=e)
            raise StopFactorServiceInvalidDataError("invalid data") from e
        except protocol.ReadStopFactorError as e:
            log.error("failed to read many stop factors by vacancy", err=e)
            raise StopFactorServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read many stop factors by vacancy", err=e)
            raise StopFactorServiceError("unknown error") from e

    # ===

    def _stop_factor_key(self, stop_factor_id: StopFactorID) -> Key:
        return self._ks.key("id", str(stop_factor_id))

    def _vacancy_set_key(self, vacancy_id: VacancyID) -> Key:
        return self._ks.key("vacancy_set", str(vacancy_id))
