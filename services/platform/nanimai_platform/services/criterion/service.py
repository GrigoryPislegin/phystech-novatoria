import asyncio
from typing import final

import structlog
from pydantic import BaseModel, Field

from nanimai_platform.domain import Criterion, CriterionID, CriterionPayload, ProjectID, UserID, VacancyID
from nanimai_platform.protocols.internal import repository as protocol
from nanimai_platform.protocols.internal.repository import CriterionRepositoryProtocol
from nanimai_platform.services.cache.cache import Cache
from nanimai_platform.services.cache.keyspace import Key, Keyspace
from nanimai_platform.services.vacancy.service import VacancyService, VacancyServiceVacancyNotFoundError
from nanimai_platform.utils.asyncio_background import launch_background
from nanimai_platform.utils.logging_span import span

log = structlog.stdlib.get_logger("app.service.CriterionService")


class CriterionServiceError(Exception): ...


class CriterionServiceInvalidDataError(Exception): ...


class CriterionServiceCriterionNotFoundError(Exception): ...


class CriterionServiceVacancyNotFoundError(Exception): ...


@final
class CriterionService:
    def __init__(
        self,
        cache: Cache,
        criterion_repo: CriterionRepositoryProtocol,
        vacancy_service: VacancyService,
    ):
        self._cache = cache
        self._ks = Keyspace("criterion_service")
        self._criterion_repo = criterion_repo
        self._vacancy_service = vacancy_service

    class CreateCriterionRequest(BaseModel):
        user_id: UserID
        project_id: ProjectID
        vacancy_id: VacancyID
        criterion: str
        initial_weight: int
        weight: float = Field(default=0.0)
        calculated: bool = Field(default=False)

    @span(op="criterion_service", name="create_criterion")
    async def create(self, request: CreateCriterionRequest) -> Criterion:
        try:
            criterion = await self._criterion_repo.create_criterion(
                CriterionRepositoryProtocol.CreateCriterionRequest(
                    user_id=request.user_id,
                    project_id=request.project_id,
                    vacancy_id=request.vacancy_id,
                    criterion=request.criterion,
                    initial_weight=request.initial_weight,
                    weight=request.weight,
                    calculated=request.calculated,
                )
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._criterion_key(criterion.id), criterion)
                await self._cache.sadd(self._vacancy_set_key(request.vacancy_id), {"id": str(criterion.id)})

            update_cache()

            return criterion

        except protocol.VacancyNotFoundError as e:
            log.error("failed to find vacancy", err=e)
            raise CriterionServiceVacancyNotFoundError("vaccancy not found") from e
        except protocol.CriterionValidateError as e:
            log.error("failed to create criterion due to validation error", err=e)
            raise CriterionServiceInvalidDataError("invalid data") from e
        except protocol.CreateCriterionError as e:
            log.error("failed to create criterion", err=e)
            raise CriterionServiceError("failed to create") from e
        except Exception as e:
            log.error("failed to create criterion", err=e)
            raise CriterionServiceError("unknown error") from e

    class CreateManyCriteriaRequest(BaseModel):
        user_id: UserID
        project_id: ProjectID
        vacancy_id: VacancyID
        criteria: list[CriterionPayload]

    @span(op="criterion_service", name="create_many_criteria")
    async def create_many(self, request: CreateManyCriteriaRequest) -> list[CriterionID]:
        try:
            criterion_ids = await self._criterion_repo.create_many_criteria(
                CriterionRepositoryProtocol.CreateManyCriteriaRequest(
                    user_id=request.user_id,
                    project_id=request.project_id,
                    vacancy_id=request.vacancy_id,
                    criteria=request.criteria,
                )
            )

            @launch_background
            async def update_cache():
                ids = [{"id": str(cr_id)} for cr_id in criterion_ids]

                await self._cache.sadd(self._vacancy_set_key(request.vacancy_id), *ids)

            update_cache()

            return criterion_ids

        except protocol.VacancyNotFoundError as e:
            log.error("failed to find vacancy", err=e)
            raise CriterionServiceVacancyNotFoundError("vacancy not found") from e
        except protocol.CriterionValidateError as e:
            log.error("failed to create criterion due to validation error", err=e)
            raise CriterionServiceInvalidDataError("invalid data") from e
        except protocol.CreateCriterionError as e:
            log.error("failed to create criterion", err=e)
            raise CriterionServiceError("failed to create") from e
        except Exception as e:
            log.error("failed to create criterion", err=e)
            raise CriterionServiceError("unknown error") from e

    class ReadCriterionRequest(BaseModel):
        id: CriterionID

    @span(op="criterion_service", name="read_criterion")
    async def read(self, request: ReadCriterionRequest) -> Criterion:
        try:
            if (criterion := await self._cache.get(self._criterion_key(request.id), t=Criterion)) is not None:
                return criterion

            criterion = await self._criterion_repo.read_criterion(
                CriterionRepositoryProtocol.ReadCriterionRequest(id=request.id)
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._criterion_key(criterion.id), criterion)
                await self._cache.sadd(self._vacancy_set_key(criterion.vacancy_id), {"id": str(criterion.id)})

            update_cache()

            return criterion

        except protocol.CriterionNotFoundError as e:
            log.error("failed to find criterion", err=e)
            raise CriterionServiceCriterionNotFoundError("criterion not found") from e
        except protocol.CriterionValidateError as e:
            log.error("failed to read criterion due to validation error", err=e)
            raise CriterionServiceInvalidDataError("invalid data") from e
        except protocol.ReadCriterionError as e:
            log.error("failed to read criterion", err=e)
            raise CriterionServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read criterion", err=e)
            raise CriterionServiceError("unknown error") from e

    class ReadManyCriteriaRequest(BaseModel):
        criterion_ids: list[CriterionID]

    @span(op="criterion_service", name="read_many_criteria")
    async def read_many(self, request: ReadManyCriteriaRequest) -> list[Criterion | None]:  # noqa: C901
        try:
            criteria: dict[CriterionID, Criterion] = {}

            cache_criteria = await self._cache.mget(
                [self._criterion_key(cr_id) for cr_id in request.criterion_ids], t=Criterion
            )

            for criterion in cache_criteria:
                if criterion is not None:
                    criteria[criterion.id] = criterion

            retrieve_from_db = list(set(request.criterion_ids) - set(criteria.keys()))

            db_criteria = await self._criterion_repo.read_many_criteria(
                CriterionRepositoryProtocol.ReadManyCriteriaRequest(criterion_ids=retrieve_from_db)
            )
            for criterion in db_criteria:
                if criterion is not None:
                    criteria[criterion.id] = criterion

            @launch_background
            async def update_cache():
                if criteria:
                    await self._cache.mset({
                        self._criterion_key(cr_id): criterion for cr_id, criterion in criteria.items()
                    })

                grouped_by_vacancy: dict[VacancyID, list[dict[str, str]]] = {}
                for criterion in criteria.values():
                    if criterion.vacancy_id not in grouped_by_vacancy:
                        grouped_by_vacancy[criterion.vacancy_id] = []
                    grouped_by_vacancy[criterion.vacancy_id].append({"id": str(criterion.id)})

                _ = await asyncio.gather(*[
                    self._cache.sadd(self._vacancy_set_key(vacancy_id), *criterion_ids)
                    for vacancy_id, criterion_ids in grouped_by_vacancy.items()
                ])

            update_cache()

            return [criteria.get(criterion_id, None) for criterion_id in request.criterion_ids]

        except protocol.CriterionValidateError as e:
            log.error("failed to read criterion due to validation error", err=e)
            raise CriterionServiceInvalidDataError("invalid data") from e
        except protocol.ReadCriterionError as e:
            log.error("failed to read criterion", err=e)
            raise CriterionServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read criterion", err=e)
            raise CriterionServiceError("unknown error") from e

    class UpdateCriterionRequest(BaseModel):
        id: CriterionID

        criterion: str | None = None
        initial_weight: int | None = None

    @span(op="criterion_service", name="update_criterion")
    async def update(self, request: UpdateCriterionRequest) -> Criterion:
        try:
            criterion = await self._criterion_repo.update_criterion(
                CriterionRepositoryProtocol.UpdateCriterionRequest(
                    id=request.id,
                    criterion=request.criterion,
                    initial_weight=request.initial_weight,
                )
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._criterion_key(criterion.id), criterion)
                await self._cache.sadd(self._vacancy_set_key(criterion.vacancy_id), {"id": str(criterion.id)})

            update_cache()

            return criterion

        except protocol.CriterionNotFoundError as e:
            log.error("failed to find criterion", err=e)
            raise CriterionServiceCriterionNotFoundError("criterion not found") from e
        except protocol.CriterionValidateError as e:
            log.error("failed to update criterion due to validation error", err=e)
            raise CriterionServiceInvalidDataError("invalid data") from e
        except protocol.UpdateCriterionError as e:
            log.error("failed to update criterion", err=e)
            raise CriterionServiceError("failed to update") from e
        except Exception as e:
            log.error("failed to update criterion", err=e)
            raise CriterionServiceError("unknown error") from e

    class DeleteCriterionRequest(BaseModel):
        id: CriterionID

    @span(op="criterion_service", name="delete_criterion")
    async def delete(self, request: DeleteCriterionRequest) -> Criterion:
        try:
            criterion = await self._criterion_repo.delete_criterion(
                CriterionRepositoryProtocol.DeleteCriterionRequest(id=request.id)
            )

            await self._cache.invalidate(self._criterion_key(criterion.id))
            await self._cache.srem(self._vacancy_set_key(criterion.vacancy_id), {"id": str(criterion.id)})

            return criterion
        except protocol.CriterionNotFoundError as e:
            log.error("failed to find criterion", err=e)
            raise CriterionServiceCriterionNotFoundError("criterion not found") from e
        except protocol.CriterionValidateError as e:
            log.error("failed to delete criterion due to validation error", err=e)
            raise CriterionServiceInvalidDataError("invalid data") from e
        except protocol.DeleteCriterionError as e:
            log.error("failed to delete criterion", err=e)
            raise CriterionServiceError("failed to delete") from e
        except Exception as e:
            log.error("failed to delete criterion", err=e)
            raise CriterionServiceError("unknown error") from e

    class ReadManyCriteriaByVacancyRequest(BaseModel):
        vacancy_id: VacancyID

    @span(op="criterion_service", name="read_many_criteria_by_vacancy")
    async def read_many_by_vacancy(self, request: ReadManyCriteriaByVacancyRequest) -> list[Criterion]:  # noqa: C901
        try:
            criteria: dict[CriterionID, Criterion] = {}

            _ = await self._vacancy_service.read(self._vacancy_service.ReadVacancyRequest(id=request.vacancy_id))

            criteria_set: list[str] = [
                d["id"] for d in (await self._cache.smembers(self._vacancy_set_key(request.vacancy_id)))
            ]
            log.info("retrieved criteria set from cache", count=len(criteria_set))

            if not criteria_set:
                db_only_criteria = await self._criterion_repo.read_many_criteria_by_vacancy(
                    CriterionRepositoryProtocol.ReadManyCriteriaByVacancyRequest(vacancy_id=request.vacancy_id)
                )
                log.info("retrieved criteria from db", count=len(db_only_criteria))

                @launch_background
                async def update_cache_from_db():
                    log.info("invalidating vacancy set cache for criteria", vacancy_id=request.vacancy_id)
                    await self._cache.invalidate(self._vacancy_set_key(request.vacancy_id))

                    if db_only_criteria:
                        await self._cache.mset({
                            self._criterion_key(criterion.id): criterion for criterion in db_only_criteria
                        })
                        await self._cache.sadd(
                            self._vacancy_set_key(request.vacancy_id),
                            *[{"id": str(criterion.id)} for criterion in db_only_criteria],
                        )

                update_cache_from_db()

                return db_only_criteria

            cache_criteria = await self._cache.mget(
                [self._criterion_key(CriterionID(criteria_id)) for criteria_id in criteria_set], t=Criterion
            )
            log.info("retrieved criteria entities from cache", count=len(cache_criteria))

            from_cache = 0
            for criterion in cache_criteria:
                if criterion is not None:
                    criteria[criterion.id] = criterion
                    from_cache += 1

            retrieve_from_db = list({CriterionID(cr_id) for cr_id in criteria_set} - set(criteria.keys()))
            db_criteria = await self._criterion_repo.read_many_criteria(
                CriterionRepositoryProtocol.ReadManyCriteriaRequest(criterion_ids=retrieve_from_db)
            )
            log.info("retrieved criteria from db", count=len(db_criteria))
            from_db = 0
            for criterion in db_criteria:
                if criterion is not None:
                    criteria[criterion.id] = criterion
                    from_db += 1

            log.info(
                "cache hit statistics: criteria retrieved",
                count=len(criteria),
                cache_hit_ratio=from_cache / len(criteria),
                db_hit_ratio=from_db / len(criteria),
            )

            @launch_background
            async def update_cache():
                log.info("invalidating vacancy set cache for criteria", vacancy_id=request.vacancy_id)
                await self._cache.invalidate(self._vacancy_set_key(request.vacancy_id))

                if criteria:
                    await self._cache.mset({
                        self._criterion_key(criterion.id): criterion for criterion in criteria.values()
                    })
                    await self._cache.sadd(
                        self._vacancy_set_key(request.vacancy_id),
                        *[{"id": str(criterion.id)} for criterion in criteria.values()],
                    )

            update_cache()

            return list(criteria.values())
        except VacancyServiceVacancyNotFoundError as e:
            log.error("failed to find vacancy", err=e)
            raise CriterionServiceVacancyNotFoundError("vacancy not found") from e
        except protocol.CriterionValidateError as e:
            log.error("failed to read many criteria due to validation error", err=e)
            raise CriterionServiceInvalidDataError("invalid data") from e
        except protocol.ReadCriterionError as e:
            log.error("failed to read many criteria by vacancy", err=e)
            raise CriterionServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read many criteria by vacancy", err=e)
            raise CriterionServiceError("unknown error") from e

    # ===

    def _criterion_key(self, criterion_id: CriterionID) -> Key:
        return self._ks.key("id", str(criterion_id))

    def _vacancy_set_key(self, vacancy_id: VacancyID) -> Key:
        return self._ks.key("vacancy_set", str(vacancy_id))
