from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import final

import structlog
from deprecated import deprecated
from pydantic import BaseModel, Field
from pydantic_core import Url

from nanimai_platform.domain import (
    AnalysisID,
    Candidate,
    CandidateCard,
    CandidateID,
    CandidateSourceEnum,
    ContactTypeEnum,
    CriterionAnalysis,
    CriterionID,
    CriterionStatusEnum,
    ExpectedSalary,
    ProjectID,
    Skill,
    StopFactorAnalysis,
    StopFactorID,
    UserID,
    VacancyID,
    VacancyStageEnum,
)
from nanimai_platform.domain.candidate.candidate import CandidateAnalysisStatusEnum
from nanimai_platform.protocols.internal import repository as protocol
from nanimai_platform.protocols.internal.repository.candidate import CandidateRepositoryProtocol
from nanimai_platform.services.cache.cache import Cache
from nanimai_platform.services.cache.keyspace import Key, Keyspace
from nanimai_platform.services.project.service import ProjectService, ProjectServiceProjectNotFoundError
from nanimai_platform.services.thumbnail.service import ThumbnailService
from nanimai_platform.services.update_stream.service import EventType, UpdateStreamService
from nanimai_platform.services.vacancy.service import VacancyService, VacancyServiceVacancyNotFoundError
from nanimai_platform.utils.asyncio_background import launch_background
from nanimai_platform.utils.logging_span import span
from nanimai_platform.utils.update_value import UpdateValue

log = structlog.stdlib.get_logger("app.service.CandidateService")


class CandidateServiceError(Exception): ...


class CandidateServiceInvalidDataError(Exception): ...


class CandidateServiceCandidateNotFoundError(Exception): ...


class CandidateServiceVacancyNotFoundError(Exception): ...


class CandidateServiceProjectNotFoundError(Exception): ...


@final
class CandidateService:
    def __init__(
        self,
        cache: Cache,
        candidate_repo: CandidateRepositoryProtocol,
        vacancy_service: VacancyService,
        project_service: ProjectService,
        thumbnail_service: ThumbnailService,
        update_stream: UpdateStreamService,
    ):
        self._cache = cache
        self._ks = Keyspace("candidate_service")
        self._candidate_repo = candidate_repo
        self._vacancy_service = vacancy_service
        self._project_service = project_service
        self._thumbnail_service = thumbnail_service
        self._update_stream = update_stream

    class CreateCandidateRequest(BaseModel):
        user_id: UserID
        project_id: ProjectID
        vacancy_id: VacancyID
        resume: str
        name: str
        city: str | None = None
        country: str | None = None
        phone_number: str | None = None
        email: str | None = None
        website: Url | None = None
        experience: int = 0
        expected_salary: ExpectedSalary | None = None
        notes: str = ""
        dirty: bool = False
        source: CandidateSourceEnum = CandidateSourceEnum.NANIMAI
        skills: list[Skill]
        status: VacancyStageEnum | None = None
        analyses: list[AnalysisID] = Field(default_factory=list)
        criteria: dict[CriterionID, CriterionAnalysis] | None = None
        stop_factors: dict[StopFactorID, StopFactorAnalysis] | None = None
        contacts: dict[ContactTypeEnum, str] | None = None

    @staticmethod
    def _extract_contacts_from_resume(resume: str) -> dict[ContactTypeEnum, str]:
        contacts: dict[ContactTypeEnum, str] = {}

        if match := re.search(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", resume, flags=re.IGNORECASE):
            contacts[ContactTypeEnum.EMAIL] = match.group(0)

        if match := re.search(
            r"(?:\+?7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}", resume, flags=re.IGNORECASE
        ):
            contacts[ContactTypeEnum.PHONE] = match.group(0)

        all_telegram_matches: list[tuple[str, int]] = []
        for match in re.finditer(r"t\.me/([a-zA-Z][a-zA-Z0-9_]{4,31})", resume):
            username = match.group(1)
            if not username.lower().endswith("bot"):
                all_telegram_matches.append(("t.me/" + username, match.start()))

        for match in re.finditer(r"(?<![a-zA-Z0-9._%+-])@([a-zA-Z][a-zA-Z0-9_]{4,31})", resume):
            username = match.group(1)
            if not username.lower().endswith("bot"):
                all_telegram_matches.append(("t.me/" + username, match.start()))

        # Sort by position and take the LAST valid one
        if all_telegram_matches:
            all_telegram_matches.sort(key=lambda x: x[1])
            contacts[ContactTypeEnum.TELEGRAM] = all_telegram_matches[-1][0]

        if match := re.search(r"wa\.me/(\+?\d{10,15})", resume, flags=re.IGNORECASE):
            contacts[ContactTypeEnum.WHATSAPP] = match.group(0)

        return contacts

    @span(op="candidate_service", name="create_candidate")
    async def create(self, request: CreateCandidateRequest) -> Candidate:
        try:
            thumbnail_url = await self._thumbnail_service.create_candidate_thumbnail(request.name)

            contacts = self._extract_contacts_from_resume(request.resume)
            contacts = contacts | (request.contacts or {})

            if ContactTypeEnum.PHONE not in contacts and request.phone_number is not None:
                contacts[ContactTypeEnum.PHONE] = request.phone_number

            if ContactTypeEnum.EMAIL not in contacts and request.email is not None:
                contacts[ContactTypeEnum.EMAIL] = request.email

            candidate = await self._candidate_repo.create_candidate(
                CandidateRepositoryProtocol.CreateCandidateRequest(
                    user_id=request.user_id,
                    project_id=request.project_id,
                    vacancy_id=request.vacancy_id,
                    resume=request.resume,
                    name=request.name,
                    city=request.city,
                    country=request.country,
                    phone_number=contacts.get(ContactTypeEnum.PHONE),
                    email=contacts.get(ContactTypeEnum.EMAIL),
                    website=request.website,
                    thumbnail_url=thumbnail_url,
                    experience=request.experience,
                    expected_salary=request.expected_salary,
                    notes=request.notes,
                    dirty=request.dirty,
                    source=request.source,
                    skills=request.skills,
                    status=request.status or VacancyStageEnum.MAGIC_AI,
                    criteria=request.criteria,
                    stop_factors=request.stop_factors,
                    analysis_status=CandidateAnalysisStatusEnum.PENDING,
                    contacts=contacts,
                )
            )

            await self._cache.invalidate(self._today_vacancy_key(candidate.vacancy_id))
            await self._cache.invalidate(self._vacancy_set_cards_key(candidate.vacancy_id))

            @launch_background
            async def update_cache():
                await self._cache.set(self._candidate_key(candidate.id), candidate)
                await self._cache.sadd(self._vacancy_set_key(candidate.vacancy_id), {"id": str(candidate.id)})

                await self._cache.sadd(self._project_set_key(candidate.project_id), {"id": str(candidate.id)})
                await self._update_stream.push(
                    UpdateStreamService.PushRequest(
                        user_id=request.user_id,
                        event_type=EventType.CREATED,
                        entity=candidate,
                    )
                )

            update_cache()

            return candidate

        except protocol.VacancyNotFoundError as e:
            log.error("failed to find vacancy", err=e)
            raise CandidateServiceVacancyNotFoundError("vacancy not found") from e
        except protocol.CandidateValidateError as e:
            log.error("failed to create candidate due to validation error", err=e)
            raise CandidateServiceInvalidDataError("invalid data") from e
        except protocol.CreateCandidateError as e:
            log.error("failed to create candidate", err=e)
            raise CandidateServiceError("failed to create") from e
        except Exception as e:
            log.error("failed to create candidate", err=e)
            raise CandidateServiceError("unknown error") from e

    class ReadCandidateRequest(BaseModel):
        id: CandidateID

    @span(op="candidate_service", name="read_candidate")
    async def read(self, request: ReadCandidateRequest) -> Candidate:
        try:
            if (candidate := await self._cache.get(self._candidate_key(request.id), t=Candidate)) is not None:
                return candidate

            candidate = await self._candidate_repo.read_candidate(
                CandidateRepositoryProtocol.ReadCandidateRequest(id=request.id)
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._candidate_key(candidate.id), candidate)
                await self._cache.sadd(self._vacancy_set_key(candidate.vacancy_id), {"id": str(candidate.id)})
                await self._cache.sadd(self._project_set_key(candidate.project_id), {"id": str(candidate.id)})

            update_cache()

            return candidate
        except protocol.CandidateValidateError as e:
            log.error("failed to read candidate due to validation error", err=e)
            raise CandidateServiceInvalidDataError("invalid data") from e
        except protocol.CandidateNotFoundError as e:
            log.error("failed to find candidate", err=e)
            raise CandidateServiceCandidateNotFoundError("failed to find") from e
        except protocol.ReadCandidateError as e:
            log.error("failed to read candidate", err=e)
            raise CandidateServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read candidate", err=e)
            raise CandidateServiceError("unknown error") from e

    class ReadManyCandidatesRequest(BaseModel):
        candidate_ids: list[CandidateID]

    @span(op="candidate_service", name="read_many_candidates")
    async def read_many(self, request: ReadManyCandidatesRequest) -> list[Candidate | None]:  # noqa: C901
        try:
            candidates: dict[CandidateID, Candidate] = {}

            # try to load as much as possible from cache
            cache_candidates = await self._cache.mget(
                [self._candidate_key(id) for id in request.candidate_ids], t=Candidate
            )
            for candidate in cache_candidates:
                if candidate is not None:
                    candidates[candidate.id] = candidate  # store results

            # retrieve from db the rest
            retrieve_from_db = list(set(request.candidate_ids) - set(candidates.keys()))

            db_candidates = await self._candidate_repo.read_many_candidates(
                CandidateRepositoryProtocol.ReadManyCandidatesRequest(candidate_ids=retrieve_from_db)
            )
            for candidate in db_candidates:
                if candidate is not None:
                    candidates[candidate.id] = candidate

            @launch_background
            async def update_cache():
                # save candidates to cache and add to vacancy set
                if candidates:
                    await self._cache.mset({self._candidate_key(id): candidate for id, candidate in candidates.items()})

                grouped_by_vacancy: dict[VacancyID, list[dict[str, str]]] = {}
                for candidate in candidates.values():
                    if candidate.vacancy_id not in grouped_by_vacancy:
                        grouped_by_vacancy[candidate.vacancy_id] = []
                    grouped_by_vacancy[candidate.vacancy_id].append({"id": str(candidate.id)})

                grouped_by_project: dict[ProjectID, list[dict[str, str]]] = {}
                for candidate in candidates.values():
                    if candidate.project_id not in grouped_by_project:
                        grouped_by_project[candidate.project_id] = []
                    grouped_by_project[candidate.project_id].append({"id": str(candidate.id)})

                _ = await asyncio.gather(*[
                    self._cache.sadd(self._vacancy_set_key(vacancy_id), *candidate_ids)
                    for vacancy_id, candidate_ids in grouped_by_vacancy.items()
                ])
                _ = await asyncio.gather(*[
                    self._cache.sadd(self._project_set_key(project_id), *candidate_ids)
                    for project_id, candidate_ids in grouped_by_project.items()
                ])

            update_cache()

            # return candidates in the same order as requested
            return [candidates.get(candidate_id, None) for candidate_id in request.candidate_ids]
        except protocol.CandidateValidateError as e:
            log.error("failed to read many candidates due to validation error", err=e)
            raise CandidateServiceInvalidDataError("invalid data") from e
        except protocol.ReadCandidateError as e:
            log.error("failed to read many candidates", err=e)
            raise CandidateServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read many candidates", err=e)
            raise CandidateServiceError("unknown error") from e

    class UpdateCandidateRequest(BaseModel):
        id: CandidateID
        resume: UpdateValue[str] | None = None
        name: UpdateValue[str] | None = None
        city: UpdateValue[str | None] | None = None
        country: UpdateValue[str | None] | None = None
        phone_number: UpdateValue[str | None] | None = None
        email: UpdateValue[str | None] | None = None
        website: UpdateValue[Url | None] | None = None
        thumbnail_url: UpdateValue[str] | None = None
        experience: UpdateValue[int] | None = None
        expected_salary: UpdateValue[ExpectedSalary | None] | None = None
        notes: UpdateValue[str] | None = None
        dirty: UpdateValue[bool] | None = None
        source: UpdateValue[CandidateSourceEnum] | None = None
        skills: UpdateValue[list[Skill]] | None = None
        status: UpdateValue[VacancyStageEnum] | None = None
        analysis_status: UpdateValue[CandidateAnalysisStatusEnum] | None = None
        contacts: UpdateValue[dict[ContactTypeEnum, str]] | None = None

    @span(op="candidate_service", name="update_candidate")
    async def update(self, request: UpdateCandidateRequest) -> Candidate:
        try:
            new_status_history: UpdateValue[set[VacancyStageEnum]] | None = None
            if isinstance(request.status, UpdateValue):
                current_candidate = await self._candidate_repo.read_candidate(
                    CandidateRepositoryProtocol.ReadCandidateRequest(id=request.id)
                )
                new_status_history = UpdateValue(current_candidate.status_history | {request.status.value})
            dirty = request.dirty if isinstance(request.dirty, UpdateValue) else UpdateValue(True)

            candidate = await self._candidate_repo.update_candidate(
                CandidateRepositoryProtocol.UpdateCandidateRequest(
                    id=request.id,
                    resume=request.resume,
                    name=request.name,
                    city=request.city,
                    country=request.country,
                    phone_number=request.phone_number,
                    email=request.email,
                    website=request.website,
                    thumbnail_url=request.thumbnail_url,
                    experience=request.experience,
                    expected_salary=request.expected_salary,
                    notes=request.notes,
                    dirty=dirty,
                    source=request.source,
                    skills=request.skills,
                    status=request.status,
                    status_history=new_status_history,
                    analysis_status=request.analysis_status,
                    contacts=request.contacts,
                )
            )

            await self._cache.invalidate(self._vacancy_set_cards_key(candidate.vacancy_id))

            @launch_background
            async def update_cache():
                await self._cache.set(self._candidate_key(candidate.id), candidate)
                await self._cache.sadd(self._vacancy_set_key(candidate.vacancy_id), {"id": str(candidate.id)})
                await self._cache.sadd(self._project_set_key(candidate.project_id), {"id": str(candidate.id)})
                await self._update_stream.push(
                    UpdateStreamService.PushRequest(
                        user_id=candidate.user_id,
                        event_type=EventType.UPDATED,
                        entity=candidate,
                    )
                )

            update_cache()

            return candidate
        except protocol.CandidateValidateError as e:
            log.error("failed to update candidate due to validation error", err=e)
            raise CandidateServiceInvalidDataError("invalid data") from e
        except protocol.CandidateNotFoundError as e:
            log.error("failed to find candidate", err=e)
            raise CandidateServiceCandidateNotFoundError("failed to find") from e
        except protocol.UpdateCandidateError as e:
            log.error("failed to update candidate", err=e)
            raise CandidateServiceError("failed to update") from e
        except Exception as e:
            log.error("failed to update candidate", err=e)
            raise CandidateServiceError("unknown error") from e

    class DeleteCandidateRequest(BaseModel):
        id: CandidateID

    @span(op="candidate_service", name="delete_candidate")
    async def delete(self, request: DeleteCandidateRequest) -> Candidate:
        try:
            candidate = await self._candidate_repo.delete_candidate(
                CandidateRepositoryProtocol.DeleteCandidateRequest(id=request.id)
            )

            await self._cache.invalidate(self._candidate_key(candidate.id))
            await self._cache.srem(self._vacancy_set_key(candidate.vacancy_id), {"id": str(candidate.id)})
            await self._cache.srem(self._project_set_key(candidate.project_id), {"id": str(candidate.id)})
            await self._update_stream.push(
                UpdateStreamService.PushRequest(
                    user_id=candidate.user_id,
                    event_type=EventType.DELETED,
                    entity=candidate,
                )
            )

            return candidate
        except protocol.CandidateValidateError as e:
            log.error("failed to delete candidate due to validation error", err=e)
            raise CandidateServiceInvalidDataError("invalid data") from e
        except protocol.CandidateNotFoundError as e:
            log.error("failed to find candidate", err=e)
            raise CandidateServiceCandidateNotFoundError("invalid data") from e
        except protocol.DeleteCandidateError as e:
            log.error("failed to delete candidate", err=e)
            raise CandidateServiceError("failed to delete") from e
        except Exception as e:
            log.error("failed to delete candidate", err=e)
            raise CandidateServiceError("unknown error") from e

    class ReadManyByProjectRequest(BaseModel):
        project_id: ProjectID

    @span(op="candidate_service", name="read_many_candidates_by_project")
    async def read_many_by_project(self, request: ReadManyByProjectRequest) -> list[Candidate]:  # noqa: C901
        try:
            candidates: dict[CandidateID, Candidate] = {}

            # assert project exists
            _ = await self._project_service.read(self._project_service.ReadProjectRequest(id=request.project_id))

            # fetch project set from cache
            candidates_set: list[str] = [
                d["id"] for d in (await self._cache.smembers(self._project_set_key(request.project_id)))
            ]
            log.info("retrieved candidates set from cache", count=len(candidates_set))

            if not candidates_set:  # cache miss
                # read from db
                db_only_candidates = await self._candidate_repo.read_many_candidates_by_project(
                    CandidateRepositoryProtocol.ReadManyCandidatesByProjectRequest(project_id=request.project_id)
                )
                log.info("retrieved candidates from db", count=len(db_only_candidates))

                @launch_background
                async def update_cache_from_db():
                    # save candidates to cache
                    log.info("invalidating project set cache for candidates", project_id=request.project_id)
                    await self._cache.invalidate(self._project_set_key(request.project_id))

                    if db_only_candidates:
                        await self._cache.mset({
                            self._candidate_key(candidate.id): candidate for candidate in db_only_candidates
                        })
                        await self._cache.sadd(
                            self._project_set_key(request.project_id), *[{"id": str(c.id)} for c in db_only_candidates]
                        )

                update_cache_from_db()
                return db_only_candidates

            # cache hit

            # read from cache
            cache_candidates = await self._cache.mget(
                [self._candidate_key(CandidateID(id)) for id in candidates_set], t=Candidate
            )
            log.info("retrieved candidates entities from cache", count=len(cache_candidates))

            from_cache = 0
            for candidate in cache_candidates:
                if candidate is not None:
                    candidates[candidate.id] = candidate
                    from_cache += 1

            # read rest from db
            db_candidates = await self._candidate_repo.read_many_candidates(
                CandidateRepositoryProtocol.ReadManyCandidatesRequest(
                    candidate_ids=list({CandidateID(id) for id in candidates_set} - set(candidates.keys()))
                )
            )
            log.info("retrieved candidates from db", count=len(db_candidates))
            from_db = 0
            for candidate in db_candidates:
                if candidate is not None:
                    candidates[candidate.id] = candidate
                    from_db += 1

            log.info(
                "cache hit statistics: candidates retrieved",
                count=len(candidates),
                cache_hit_ratio=from_cache / len(candidates),
                db_hit_ratio=from_db / len(candidates),
            )

            @launch_background
            async def update_cache():
                # save candidates to cache
                log.info("invalidating project set cache for candidates", project_id=request.project_id)
                await self._cache.invalidate(self._project_set_key(request.project_id))

                if candidates:
                    await self._cache.mset({
                        self._candidate_key(candidate.id): candidate for candidate in candidates.values()
                    })
                    await self._cache.sadd(
                        self._project_set_key(request.project_id), *[{"id": str(c.id)} for c in candidates.values()]
                    )

            update_cache()

            return list(candidates.values())

        except ProjectServiceProjectNotFoundError as e:
            log.error("failed to find project", err=e)
            raise CandidateServiceProjectNotFoundError("project not found") from e
        except protocol.CandidateValidateError as e:
            log.error("failed to read many candidates by project due to validation error", err=e)
            raise CandidateServiceInvalidDataError("invalid data") from e
        except protocol.ReadCandidateError as e:
            log.error("failed to read many candidates by project", err=e)
            raise CandidateServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read many candidates by project", err=e)
            raise CandidateServiceError("unknown error") from e

    class ReadManyByVacancyRequest(BaseModel):
        vacancy_id: VacancyID

    @deprecated(reason="use read_many_candidate_cards instead")
    @span(op="candidate_service", name="read_many_candidates_by_vacancy")
    async def read_many_by_vacancy(self, request: ReadManyByVacancyRequest) -> list[Candidate]:  # noqa: C901
        try:
            candidates: dict[CandidateID, Candidate] = {}

            # assert vacancy exists
            _ = await self._vacancy_service.read(self._vacancy_service.ReadVacancyRequest(id=request.vacancy_id))

            # fetch vacancy set from cache
            candidates_set: list[str] = [
                d["id"] for d in (await self._cache.smembers(self._vacancy_set_key(request.vacancy_id)))
            ]
            log.info("retrieved candidates set from cache", count=len(candidates_set))

            if not candidates_set:  # cache miss
                # read from db
                db_only_candidates = await self._candidate_repo.read_many_candidates_by_vacancy(
                    CandidateRepositoryProtocol.ReadManyCandidatesByVacancyRequest(vacancy_id=request.vacancy_id)
                )
                log.info("retrieved candidates from db", count=len(db_only_candidates))

                @launch_background
                async def update_cache_from_db():
                    # save candidates to cache
                    log.info("invalidating vacancy set cache for candidates", vacancy_id=request.vacancy_id)
                    await self._cache.invalidate(self._vacancy_set_key(request.vacancy_id))

                    if db_only_candidates:
                        await self._cache.mset({
                            self._candidate_key(candidate.id): candidate for candidate in db_only_candidates
                        })
                        await self._cache.sadd(
                            self._vacancy_set_key(request.vacancy_id), *[{"id": str(c.id)} for c in db_only_candidates]
                        )

                update_cache_from_db()
                return db_only_candidates

            # cache hit

            # read from cache
            cache_candidates = await self._cache.mget(
                [self._candidate_key(CandidateID(id)) for id in candidates_set], t=Candidate
            )
            log.info("retrieved candidates entities from cache", count=len(cache_candidates))

            from_cache = 0
            for candidate in cache_candidates:
                if candidate is not None:
                    candidates[candidate.id] = candidate
                    from_cache += 1

            # read rest from db
            db_candidates = await self._candidate_repo.read_many_candidates(
                CandidateRepositoryProtocol.ReadManyCandidatesRequest(
                    candidate_ids=list({CandidateID(id) for id in candidates_set} - set(candidates.keys()))
                )
            )
            log.info("retrieved candidates from db", count=len(db_candidates))
            from_db = 0
            for candidate in db_candidates:
                if candidate is not None:
                    candidates[candidate.id] = candidate
                    from_db += 1

            log.info(
                "cache hit statistics: candidates retrieved",
                count=len(candidates),
                cache_hit_ratio=from_cache / len(candidates),
                db_hit_ratio=from_db / len(candidates),
            )

            @launch_background
            async def update_cache():
                # save candidates to cache
                log.info("invalidating vacancy set cache for candidates", vacancy_id=request.vacancy_id)
                await self._cache.invalidate(self._vacancy_set_key(request.vacancy_id))

                if candidates:
                    await self._cache.mset({
                        self._candidate_key(candidate.id): candidate for candidate in candidates.values()
                    })
                    await self._cache.sadd(
                        self._vacancy_set_key(request.vacancy_id), *[{"id": str(c.id)} for c in candidates.values()]
                    )

            update_cache()

            return list(candidates.values())
        except VacancyServiceVacancyNotFoundError as e:
            log.error("failed to find vacancy", err=e)
            raise CandidateServiceVacancyNotFoundError("vacancy not found") from e
        except protocol.CandidateValidateError as e:
            log.error("failed to read many candidates by vacancy due to validation error", err=e)
            raise CandidateServiceInvalidDataError("invalid data") from e
        except protocol.ReadCandidateError as e:
            log.error("failed to read many candidates by vacancy", err=e)
            raise CandidateServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read many candidates by vacancy", err=e)
            raise CandidateServiceError("unknown error") from e

    class UpdateCandidateCriterionRequest(BaseModel):
        id: CandidateID

        criterion_id: CriterionID
        score: UpdateValue[float | None] | None
        status: UpdateValue[CriterionStatusEnum | None] | None
        description: UpdateValue[str | None] | None

    @span(op="candidate_service", name="update_candidate_criterion")
    async def update_candidate_criterion(self, request: UpdateCandidateCriterionRequest) -> Candidate:
        try:
            candidate = await self._candidate_repo.update_candidate_criterion(
                CandidateRepositoryProtocol.UpdateCandidateCriterionRequest(
                    id=request.id,
                    criterion_id=request.criterion_id,
                    score=request.score,
                    status=request.status,
                    description=request.description,
                )
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._candidate_key(candidate.id), candidate)
                await self._cache.sadd(self._vacancy_set_key(candidate.vacancy_id), {"id": str(candidate.id)})
                await self._cache.sadd(self._project_set_key(candidate.project_id), {"id": str(candidate.id)})
                await self._update_stream.push(
                    UpdateStreamService.PushRequest(
                        user_id=candidate.user_id,
                        event_type=EventType.UPDATED,
                        entity=candidate,
                    )
                )

            update_cache()

            return candidate
        except protocol.CandidateValidateError as e:
            log.error("failed to update candidate criterion due to validation error", err=e)
            raise CandidateServiceInvalidDataError("invalid data") from e
        except protocol.CandidateNotFoundError as e:
            log.error("failed to find candidate", err=e)
            raise CandidateServiceCandidateNotFoundError("failed to find") from e
        except protocol.UpdateCandidateError as e:
            log.error("failed to update candidate criterion", err=e)
            raise CandidateServiceError("failed to update") from e
        except Exception as e:
            log.error("failed to update candidate criterion", err=e)
            raise CandidateServiceError("unknown error") from e

    class SetCandidateCriterionRequest(BaseModel):
        criterion_id: CriterionID
        score: UpdateValue[float | None] | None
        status: UpdateValue[CriterionStatusEnum | None] | None
        description: UpdateValue[str | None] | None

    class SetCandidateCriteriaRequest(BaseModel):
        id: CandidateID

        updates: list[CandidateService.SetCandidateCriterionRequest]

    @span(op="candidate_service", name="set_candidate_criteria")
    async def set_candidate_criteria(  # noqa: C901
        self, request: SetCandidateCriteriaRequest
    ) -> Candidate | None:
        try:
            if len(request.updates) == 0:
                return None

            candidate = await self._candidate_repo.set_candidate_criteria(
                CandidateRepositoryProtocol.SetCandidateCriteriaRequest(
                    id=request.id,
                    updates=[
                        CandidateRepositoryProtocol.SetCandidateCriterion(
                            criterion_id=update.criterion_id,
                            score=update.score,
                            status=update.status,
                            description=update.description,
                        )
                        for update in request.updates
                    ],
                )
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._candidate_key(candidate.id), candidate)
                await self._cache.sadd(self._vacancy_set_key(candidate.vacancy_id), {"id": str(candidate.id)})
                await self._cache.sadd(self._project_set_key(candidate.project_id), {"id": str(candidate.id)})
                await self._update_stream.push(
                    UpdateStreamService.PushRequest(
                        user_id=candidate.user_id,
                        event_type=EventType.UPDATED,
                        entity=candidate,
                    )
                )

            update_cache()

            return candidate
        except protocol.CandidateValidateError as e:
            log.error("failed to set candidate criteria due to validation error", err=e)
            raise CandidateServiceInvalidDataError("invalid data") from e
        except protocol.CandidateNotFoundError as e:
            log.error("failed to find candidate", err=e)
            raise CandidateServiceCandidateNotFoundError("failed to find") from e
        except protocol.UpdateCandidateError as e:
            log.error("failed to set candidate criteria", err=e)
            raise CandidateServiceError("failed to update") from e
        except Exception as e:
            log.error("failed to set candidate criteria", err=e)
            raise CandidateServiceError("unknown error") from e

    class UpdateCandidateStopFactorRequest(BaseModel):
        id: CandidateID

        stop_factor_id: StopFactorID
        status: UpdateValue[bool | None] | None
        description: UpdateValue[str | None] | None

    @span(op="candidate_service", name="update_candidate_stop_factor")
    async def update_candidate_stop_factor(self, request: UpdateCandidateStopFactorRequest) -> Candidate:
        try:
            candidate = await self._candidate_repo.update_candidate_stop_factor(
                CandidateRepositoryProtocol.UpdateCandidateStopFactorRequest(
                    id=request.id,
                    stop_factor_id=request.stop_factor_id,
                    status=request.status,
                    description=request.description,
                )
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._candidate_key(candidate.id), candidate)
                await self._cache.sadd(self._vacancy_set_key(candidate.vacancy_id), {"id": str(candidate.id)})
                await self._cache.sadd(self._project_set_key(candidate.project_id), {"id": str(candidate.id)})
                await self._update_stream.push(
                    UpdateStreamService.PushRequest(
                        user_id=candidate.user_id,
                        event_type=EventType.UPDATED,
                        entity=candidate,
                    )
                )

            update_cache()

            return candidate
        except protocol.CandidateValidateError as e:
            log.error("failed to update candidate stop factor due to validation error", err=e)
            raise CandidateServiceInvalidDataError("invalid data") from e
        except protocol.CandidateNotFoundError as e:
            log.error("failed to find candidate", err=e)
            raise CandidateServiceCandidateNotFoundError("failed to find") from e
        except protocol.UpdateCandidateError as e:
            log.error("failed to update candidate stop factor", err=e)
            raise CandidateServiceError("failed to update") from e
        except Exception as e:
            log.error("failed to update candidate stop factor", err=e)
            raise CandidateServiceError("unknown error") from e

    class SetCandidateStopFactorRequest(BaseModel):
        stop_factor_id: StopFactorID
        status: UpdateValue[bool | None] | None
        description: UpdateValue[str | None] | None

    class SetCandidateStopFactorsRequest(BaseModel):
        id: CandidateID

        updates: list[CandidateService.SetCandidateStopFactorRequest]

    @span(op="candidate_service", name="set_candidate_stop_factors")
    async def set_candidate_stop_factors(  # noqa: C901
        self, request: SetCandidateStopFactorsRequest
    ) -> Candidate | None:
        try:
            if len(request.updates) == 0:
                return None

            candidate = await self._candidate_repo.set_candidate_stop_factors(
                CandidateRepositoryProtocol.SetCandidateStopFactorsRequest(
                    id=request.id,
                    updates=[
                        CandidateRepositoryProtocol.SetCandidateStopFactor(
                            stop_factor_id=update.stop_factor_id,
                            status=update.status,
                            description=update.description,
                        )
                        for update in request.updates
                    ],
                )
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._candidate_key(candidate.id), candidate)
                await self._cache.sadd(self._vacancy_set_key(candidate.vacancy_id), {"id": str(candidate.id)})
                await self._cache.sadd(self._project_set_key(candidate.project_id), {"id": str(candidate.id)})
                await self._update_stream.push(
                    UpdateStreamService.PushRequest(
                        user_id=candidate.user_id,
                        event_type=EventType.UPDATED,
                        entity=candidate,
                    )
                )

            update_cache()

            return candidate
        except protocol.CandidateValidateError as e:
            log.error("failed to set candidate stop-factors due to validation error", err=e)
            raise CandidateServiceInvalidDataError("invalid data") from e
        except protocol.CandidateNotFoundError as e:
            log.error("failed to find candidate", err=e)
            raise CandidateServiceCandidateNotFoundError("failed to find") from e
        except protocol.UpdateCandidateError as e:
            log.error("failed to set candidate stop-factors", err=e)
            raise CandidateServiceError("failed to update") from e
        except Exception as e:
            log.error("failed to set candidate stop-factors", err=e)
            raise CandidateServiceError("unknown error") from e

    class ReadManyCandidateCardsRequest(BaseModel):
        vacancy_id: VacancyID
        resume: str | None = None
        name: str | None = None
        phone: str | None = None
        email: str | None = None
        city: str | None = None
        country: str | None = None
        notes: str | None = None

    @span(op="candidate_service", name="read_many_candidate_cards")
    async def read_many_candidate_cards(self, request: ReadManyCandidateCardsRequest) -> list[CandidateCard]:  # noqa: C901
        try:
            # Check if any filters are provided
            has_filters = any([
                request.resume,
                request.name,
                request.phone,
                request.email,
                request.city,
                request.country,
                request.notes,
            ])

            # Only use cache if no filters are provided
            if not has_filters:
                if (
                    box := await self._cache.get(self._vacancy_set_cards_key(request.vacancy_id), t=self.CardSet)
                ) is not None:
                    return box.cards

            cards = await self._candidate_repo.read_many_candidate_cards(
                CandidateRepositoryProtocol.ReadManyCandidateCards(
                    vacancy_id=request.vacancy_id,
                    resume=request.resume,
                    name=request.name,
                    phone=request.phone,
                    email=request.email,
                    city=request.city,
                    country=request.country,
                    notes=request.notes,
                )
            )
            log.info("retrieved candidates cards from db", count=len(cards))
            for card in cards:
                card.notes_preview = (
                    (card.notes_preview[:27] + "...") if len(card.notes_preview) > 27 else card.notes_preview
                )

            if not has_filters:

                @launch_background
                async def update_cache():
                    await self._cache.set(self._vacancy_set_cards_key(request.vacancy_id), self.CardSet(cards=cards))

                update_cache()

            return cards

        except protocol.CandidateValidateError as e:
            log.error("failed to read many candidates by vacancy due to validation error", err=e)
            raise CandidateServiceInvalidDataError("invalid data") from e
        except protocol.ReadCandidateError as e:
            log.error("failed to read many candidates by vacancy", err=e)
            raise CandidateServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read many candidates by vacancy", err=e)
            raise CandidateServiceError("unknown error") from e

    # ===

    def _candidate_key(self, candidate_id: CandidateID) -> Key:
        return self._ks.key("id", str(candidate_id))

    def _vacancy_set_key(self, vacancy_id: VacancyID) -> Key:
        return self._ks.key("vacancy_set", str(vacancy_id))

    class CardSet(BaseModel):
        cards: list[CandidateCard]

    def _vacancy_set_cards_key(self, vacancy_id: VacancyID) -> Key:
        return self._ks.key("vacancy_set_cards", str(vacancy_id))

    def _project_set_key(self, project_id: ProjectID) -> Key:
        return self._ks.key("project_set", str(project_id))

    def _today_vacancy_key(self, vacancy_id: VacancyID) -> Key:
        today = datetime.now(UTC).date().isoformat()
        return self._ks.key("vacancy_today", str(vacancy_id), today)
