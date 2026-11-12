import asyncio
from collections import defaultdict
from datetime import UTC, datetime
from typing import final

import structlog
from pydantic import BaseModel, HttpUrl

from nanimai_platform.domain import (
    CandidateID,
    ExperienceEnum,
    Oauth2SourceEnum,
    ProjectID,
    PublicationStatus,
    PublicationStatusEnum,
    SalaryAmountRange,
    ScheduleEnum,
    Skill,
    UserID,
    Vacancy,
    VacancyID,
    VacancyPublication,
    VacancyStageEnum,
    VacancyStageStatus,
    VacancyStatus,
    WorkFormatEnum,
    WorkTypeEnum,
)
from nanimai_platform.domain.vacancy.vacancy import VacancyPublicationSourceEnum, VacancyStatistics
from nanimai_platform.protocols.external.candidate_polling import CandidatePollingProtocol
from nanimai_platform.protocols.internal.repository.project import ProjectNotFoundError
from nanimai_platform.protocols.internal.repository.vacancy import (
    CreateVacancyError,
    DeleteVacancyError,
    ReadVacancyError,
    UpdateVacancyError,
    VacancyNotFoundError,
    VacancyRepositoryProtocol,
    VacancyValidateError,
)
from nanimai_platform.services.cache.cache import Cache
from nanimai_platform.services.cache.keyspace import Key, Keyspace
from nanimai_platform.services.hharon_proxy import HHaronProxyService
from nanimai_platform.services.oauth2.service import (
    OAuth2Service,
    OAuth2ServiceEmptyTokenError,
    OAuth2ServiceError,
    OAuth2ServiceInvalidDataError,
    OAuth2ServiceOAuth2NotFoundError,
)
from nanimai_platform.services.project.service import ProjectService
from nanimai_platform.services.thumbnail.service import ThumbnailService
from nanimai_platform.services.vacancy_importer.service import (
    VacancyImporterService,
    VacancyImporterServiceError,
    VacancyImporterServiceWrongURLFormatError,
)
from nanimai_platform.utils.asyncio_background import launch_background
from nanimai_platform.utils.logging_span import span
from nanimai_platform.utils.update_value import UpdateValue

log = structlog.stdlib.get_logger("app.service.VacancyService")


class VacancyServiceError(Exception): ...


class VacancyServiceInvalidDataError(Exception): ...


class VacancyServiceWrongVacancyUrlError(Exception): ...


class VacancyServiceOAuth2Error(Exception): ...


class VacancyServiceVacancyNotFoundError(Exception): ...


class VacancyServiceProjectNotFoundError(Exception): ...


@final
class VacancyService:
    def __init__(
        self,
        cache: Cache,
        vacancy_repo: VacancyRepositoryProtocol,
        project_service: ProjectService,
        thumbnail_service: ThumbnailService,
        hh_candidate_polling_adapter: CandidatePollingProtocol,
        oauth2_service: OAuth2Service,
        vacancy_importer_service: VacancyImporterService,
        hharon_proxy: HHaronProxyService,
    ):
        self._cache = cache
        self._ks = Keyspace("vacancy_service")

        self._vacancy_repo = vacancy_repo
        self._project_service = project_service
        self._thumbnail_service = thumbnail_service
        self._hh_candidate_polling_adapter = hh_candidate_polling_adapter
        self._oauth2_service = oauth2_service
        self._vacancy_importer_service = vacancy_importer_service
        self._hharon_proxy = hharon_proxy

    class CreateVacancyRequest(BaseModel):
        user_id: UserID
        project_id: ProjectID
        title: str
        description: str
        specialization: str
        status: VacancyStatus | None = None
        city: str | None = None
        country: str | None = None
        hire_amount: int | None = None
        salary: SalaryAmountRange | None = None
        work_type: WorkTypeEnum | None = None
        work_format: list[WorkFormatEnum] | None = None
        is_internship: bool | None = None
        is_temphire: bool | None = None
        schedule: list[ScheduleEnum] | None = None
        daily_rate: list[int] | None = None
        experience: ExperienceEnum | None = None
        skills: list[Skill] | None = None
        stages: list[VacancyStageStatus] | None = None
        publication: VacancyPublication | None = None
        threshold: float

    @span(op="vacancy_service", name="create_vacancy")
    async def create(self, request: CreateVacancyRequest) -> Vacancy:
        try:
            thumbnail_url = await self._thumbnail_service.create_vacancy_thumbnail(request.title)

            vacancy = await self._vacancy_repo.create_vacancy(
                VacancyRepositoryProtocol.CreateVacancyRequest(
                    user_id=request.user_id,
                    project_id=request.project_id,
                    title=request.title.strip().capitalize(),
                    description=request.description.strip(),
                    specialization=request.specialization.strip().capitalize(),
                    thumbnail_url=thumbnail_url,
                    status=request.status or VacancyStatus.OPEN,
                    city=request.city.strip().capitalize() if request.city is not None else None,
                    country=request.country.strip().capitalize() if request.country is not None else None,
                    hire_amount=request.hire_amount,
                    salary=request.salary,
                    work_type=request.work_type or WorkTypeEnum.FULL_TIME,
                    work_format=request.work_format or [WorkFormatEnum.OFFICE],
                    is_internship=request.is_internship or False,
                    is_temphire=request.is_temphire or False,
                    schedule=request.schedule or [ScheduleEnum.SCHEDULE_5_2],
                    daily_rate=request.daily_rate or [8],
                    experience=request.experience or ExperienceEnum.EXP_0,
                    skills=request.skills or [],
                    stages=self._fix_stages(request.stages or []),
                    publication=request.publication
                    or VacancyPublication(
                        hh=PublicationStatus(
                            state=PublicationStatusEnum.NOT_PUBLISHED,
                            url=None,
                            publication_id=None,
                        ),
                        avito=PublicationStatus(
                            state=PublicationStatusEnum.NOT_PUBLISHED,
                            url=None,
                            publication_id=None,
                        ),
                    ),
                    candidates=[],
                    statistics=VacancyStatistics(total_candidates=0, platform_candidates=0, delegated_candidates=0),
                    threshold=request.threshold,
                )
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._vacancy_key(vacancy.id), vacancy)
                await self._cache.sadd(self._project_set_key(request.project_id), {"id": str(vacancy.id)})

            update_cache()

            return vacancy

        except ProjectNotFoundError as e:
            log.error("failed to find project", err=e)
            raise VacancyServiceProjectNotFoundError("project not found") from e
        except VacancyValidateError as e:
            log.error("failed to create vacancy due to validation error", err=e)
            raise VacancyServiceInvalidDataError("invalid data") from e
        except CreateVacancyError as e:
            log.error("failed to create vacancy", err=e)
            raise VacancyServiceError("failed to create") from e
        except Exception as e:
            log.error("failed to create vacancy", err=e)
            raise VacancyServiceError("unknown error") from e

    class ReadVacancyRequest(BaseModel):
        id: VacancyID

    @span(op="vacancy_service", name="read_vacancy")
    async def read(self, request: ReadVacancyRequest) -> Vacancy:
        try:
            if (vacancy := await self._cache.get(self._vacancy_key(request.id), t=Vacancy)) is not None:
                return vacancy

            vacancy = await self._vacancy_repo.read_vacancy(VacancyRepositoryProtocol.ReadVacancyRequest(id=request.id))

            @launch_background
            async def update_cache():
                await self._cache.set(self._vacancy_key(vacancy.id), vacancy)
                await self._cache.sadd(self._project_set_key(vacancy.project_id), {"id": str(vacancy.id)})

            update_cache()

            return vacancy
        except VacancyValidateError as e:
            log.error("failed to read vacancy due to validation error", err=e)
            raise VacancyServiceInvalidDataError("invalid data") from e
        except VacancyNotFoundError as e:
            log.error("failed to find vacancy", err=e)
            raise VacancyServiceVacancyNotFoundError("failed to find") from e
        except ReadVacancyError as e:
            log.error("failed to read vacancy", err=e)
            raise VacancyServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read vacancy", err=e)
            raise VacancyServiceError("unknown error") from e

    class ReadManyVacanciesRequest(BaseModel):
        vacancy_ids: list[VacancyID]

    @span(op="vacancy_service", name="read_many_vacancies")
    async def read_many(self, request: ReadManyVacanciesRequest) -> list[Vacancy | None]:  # noqa: C901
        try:
            if len(request.vacancy_ids) == 0:
                return []

            vacancies = {}

            # try to load as much as possible from cache
            cache_vacancies = await self._cache.mget([self._vacancy_key(id) for id in request.vacancy_ids], t=Vacancy)
            for vacancy in cache_vacancies:
                if vacancy is not None:
                    vacancies[vacancy.id] = vacancy  # store results

            # retrieve from db the rest
            retrieve_from_db = list(set(request.vacancy_ids) - set(vacancies.keys()))

            db_vacancies = await self._vacancy_repo.read_many_vacancies(
                VacancyRepositoryProtocol.ReadManyVacanciesRequest(vacancy_ids=retrieve_from_db)
            )
            for vacancy in db_vacancies:
                if vacancy is not None:
                    vacancies[vacancy.id] = vacancy

            @launch_background
            async def update_cache():
                # save vacancies to cache and add to project set
                if vacancies:
                    await self._cache.mset({self._vacancy_key(id): vacancy for id, vacancy in vacancies.items()})

                grouped_by_project = {}
                for vacancy in vacancies.values():
                    if vacancy.project_id not in grouped_by_project:
                        grouped_by_project[vacancy.project_id] = []
                    grouped_by_project[vacancy.project_id].append({"id": str(vacancy.id)})

                await asyncio.gather(*[
                    self._cache.sadd(self._project_set_key(project_id), *vacancy_ids)
                    for project_id, vacancy_ids in grouped_by_project.items()
                ])

            update_cache()

            # return vacancies in the same order as requested
            return [vacancies.get(vacancy_id, None) for vacancy_id in request.vacancy_ids]
        except VacancyValidateError as e:
            log.error("failed to read many vacancies due to validation error", err=e)
            raise VacancyServiceInvalidDataError("invalid data") from e
        except ReadVacancyError as e:
            log.error("failed to read many vacancies", err=e)
            raise VacancyServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read many vacancies", err=e)
            raise VacancyServiceError("unknown error") from e

    class UpdateVacancyRequest(BaseModel):
        id: VacancyID
        title: UpdateValue[str] | None = None
        description: UpdateValue[str] | None = None
        specialization: UpdateValue[str] | None = None

        thumbnail_url: UpdateValue[str] | None = None
        status: UpdateValue[VacancyStatus] | None = None
        city: UpdateValue[str | None] | None = None
        country: UpdateValue[str | None] | None = None
        hire_amount: UpdateValue[int | None] | None = None
        salary: UpdateValue[SalaryAmountRange | None] | None = None
        work_type: UpdateValue[WorkTypeEnum] | None = None
        work_format: UpdateValue[list[WorkFormatEnum]] | None = None
        is_internship: UpdateValue[bool] | None = None
        is_temphire: UpdateValue[bool] | None = None
        schedule: UpdateValue[list[ScheduleEnum]] | None = None
        daily_rate: UpdateValue[list[int]] | None = None
        experience: UpdateValue[ExperienceEnum] | None = None
        skills: UpdateValue[list[Skill]] | None = None
        stages: UpdateValue[list[VacancyStageStatus]] | None = None
        publication: UpdateValue[VacancyPublication] | None = None
        candidates: UpdateValue[list[CandidateID]] | None = None
        statistics: UpdateValue[VacancyStatistics] | None = None
        threshold: UpdateValue[float] | None = None

    @span(op="vacancy_service", name="update_vacancy")
    async def update(self, request: UpdateVacancyRequest) -> Vacancy:
        try:
            vacancy = await self._vacancy_repo.update_vacancy(
                VacancyRepositoryProtocol.UpdateVacancyRequest(
                    id=request.id,
                    title=request.title,
                    description=request.description,
                    specialization=request.specialization,
                    thumbnail_url=request.thumbnail_url,
                    status=request.status,
                    city=request.city,
                    country=request.country,
                    hire_amount=request.hire_amount,
                    salary=request.salary,
                    work_type=request.work_type,
                    work_format=request.work_format,
                    is_internship=request.is_internship,
                    is_temphire=request.is_temphire,
                    schedule=request.schedule,
                    daily_rate=request.daily_rate,
                    experience=request.experience,
                    skills=request.skills,
                    stages=request.stages,
                    publication=request.publication,
                    candidates=request.candidates,
                    statistics=request.statistics,
                    threshold=request.threshold,
                    updated_at=UpdateValue(datetime.now(UTC)),
                )
            )

            @launch_background
            async def update_cache():
                await self._cache.set(self._vacancy_key(vacancy.id), vacancy)
                await self._cache.sadd(self._project_set_key(vacancy.project_id), {"id": str(vacancy.id)})

            update_cache()

            return vacancy

        except VacancyValidateError as e:
            log.error("failed to update vacancy due to validation error", err=e)
            raise VacancyServiceInvalidDataError("invalid data") from e
        except VacancyNotFoundError as e:
            log.error("failed to find vacancy", err=e)
            raise VacancyServiceVacancyNotFoundError("failed to find") from e
        except UpdateVacancyError as e:
            log.error("failed to update vacancy", err=e)
            raise VacancyServiceError("failed to update") from e
        except Exception as e:
            log.error("failed to update vacancy", err=e)
            raise VacancyServiceError("unknown error") from e

    class DeleteVacancyRequest(BaseModel):
        id: VacancyID

    @span(op="vacancy_service", name="delete_vacancy")
    async def delete(self, request: DeleteVacancyRequest) -> Vacancy:
        try:
            vacancy = await self._vacancy_repo.delete_vacancy(
                VacancyRepositoryProtocol.DeleteVacancyRequest(id=request.id)
            )

            await self._cache.invalidate(self._vacancy_key(vacancy.id))
            await self._cache.srem(self._project_set_key(vacancy.project_id), {"id": str(vacancy.id)})

            return vacancy
        except VacancyValidateError as e:
            log.error("failed to delete vacancy due to validation error", err=e)
            raise VacancyServiceInvalidDataError("invalid data") from e
        except VacancyNotFoundError as e:
            log.error("failed to find vacancy", err=e)
            raise VacancyServiceVacancyNotFoundError("failed to find") from e
        except DeleteVacancyError as e:
            log.error("failed to delete vacancy", err=e)
            raise VacancyServiceError("failed to delete") from e
        except Exception as e:
            log.error("failed to delete vacancy", err=e)
            raise VacancyServiceError("unknown error") from e

    class ReadManyByProjectRequest(BaseModel):
        project_id: ProjectID

    @span(op="vacancy_service", name="read_many_by_project")
    async def read_many_by_project(self, request: ReadManyByProjectRequest) -> list[Vacancy]:  # noqa: C901
        try:
            vacancies: dict[VacancyID, Vacancy] = {}

            # assert project exists
            _ = await self._project_service.read(self._project_service.ReadProjectRequest(id=request.project_id))

            # fetch project set from cache
            vacancies_set: list[str] = [
                d["id"] for d in (await self._cache.smembers(self._project_set_key(request.project_id)))
            ]
            log.info("retrieved vacancies set from cache", count=len(vacancies_set))

            if not vacancies_set:  # cache miss
                # read from db
                db_only_vacancies = await self._vacancy_repo.read_many_vacancies_by_project(
                    VacancyRepositoryProtocol.ReadManyVacanciesByProjectRequest(project_id=request.project_id)
                )
                log.info("retrieved vacancies from db", count=len(db_only_vacancies))

                @launch_background
                async def update_cache():
                    log.info("invalidating project set cache for vacancies", project_id=request.project_id)
                    await self._cache.invalidate(self._project_set_key(request.project_id))
                    # save vacancies to cache
                    if db_only_vacancies:
                        await self._cache.mset({
                            self._vacancy_key(vacancy.id): vacancy for vacancy in db_only_vacancies
                        })
                        await self._cache.sadd(
                            self._project_set_key(request.project_id), *[{"id": str(v.id)} for v in db_only_vacancies]
                        )

                update_cache()

                return db_only_vacancies

            # cache hit
            cache_vacancies = await self._cache.mget(
                [self._vacancy_key(VacancyID(id)) for id in vacancies_set], t=Vacancy
            )
            log.info("retrieved vacancies entities from cache", count=len(cache_vacancies))

            # read from cache
            from_cache = 0
            for vacancy in cache_vacancies:
                if vacancy is not None:
                    vacancies[vacancy.id] = vacancy
                    from_cache += 1

            # read rest from db
            from_db = 0
            db_vacancies = await self._vacancy_repo.read_many_vacancies(
                VacancyRepositoryProtocol.ReadManyVacanciesRequest(
                    vacancy_ids=list({VacancyID(id) for id in vacancies_set} - set(vacancies.keys()))
                )
            )
            for vacancy in db_vacancies:
                if vacancy is not None:
                    vacancies[vacancy.id] = vacancy
                    from_db += 1

            log.info(
                "cache hit statistics: vacancies retrieved",
                count=len(vacancies),
                cache_hit_ratio=from_cache / len(vacancies),
                db_hit_ratio=from_db / len(vacancies),
            )

            @launch_background
            async def update_cache():
                # save vacancies to cache
                log.info("invalidating project set cache for vacancies", project_id=request.project_id)
                await self._cache.invalidate(self._project_set_key(request.project_id))

                if vacancies:
                    await self._cache.mset({self._vacancy_key(vacancy.id): vacancy for vacancy in vacancies.values()})
                    await self._cache.sadd(
                        self._project_set_key(request.project_id), *[{"id": str(v.id)} for v in vacancies.values()]
                    )

            update_cache()

            return list(vacancies.values())
        except VacancyValidateError as e:
            log.error("failed to read many vacancies by project due to validation error", err=e)
            raise VacancyServiceInvalidDataError("invalid data") from e
        except ProjectNotFoundError as e:
            log.error("failed to find project", err=e)
            raise VacancyServiceProjectNotFoundError("project not found") from e
        except ReadVacancyError as e:
            log.error("failed to read many vacancies by project", err=e)
            raise VacancyServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read many vacancies by project", err=e)
            raise VacancyServiceError("unknown error") from e

    class ReadManyPublishedVacanciesRequest(BaseModel):
        source: VacancyPublicationSourceEnum

    @span(op="vacancy_service", name="read_many_published_vacancies")
    async def read_many_published(self, request: ReadManyPublishedVacanciesRequest) -> list[Vacancy]:
        try:
            return await self._vacancy_repo.read_many_published_vacancies(
                VacancyRepositoryProtocol.ReadManyPublishedVacanciesRequest(source=request.source)
            )
        except VacancyValidateError as e:
            log.error("failed to read many published vacancies due to validation error", err=e)
            raise VacancyServiceInvalidDataError("invalid data") from e
        except ReadVacancyError as e:
            log.error("failed to read many published vacancies", err=e)
            raise VacancyServiceError("failed to read") from e
        except Exception as e:
            log.error("failed to read many published vacancies", err=e)
            raise VacancyServiceError("unknown error") from e

    def _fix_stages(self, stages: list[VacancyStageStatus]) -> list[VacancyStageStatus]:
        is_present = defaultdict(lambda: False)
        default = [
            VacancyStageStatus(stage=VacancyStageEnum.REJECTED_USER, shown=True),
            VacancyStageStatus(stage=VacancyStageEnum.REJECTED_AI, shown=True),
            VacancyStageStatus(stage=VacancyStageEnum.MAGIC_AI, shown=True),
            VacancyStageStatus(stage=VacancyStageEnum.SELECTED_AI, shown=True),
            VacancyStageStatus(stage=VacancyStageEnum.SELECTED_USER, shown=True),
            VacancyStageStatus(stage=VacancyStageEnum.MESSAGE, shown=True),
            VacancyStageStatus(stage=VacancyStageEnum.PRELIMINARY_CALL, shown=True),
            VacancyStageStatus(stage=VacancyStageEnum.INTERVIEW, shown=True),
            VacancyStageStatus(stage=VacancyStageEnum.TEST_TASK, shown=True),
            VacancyStageStatus(stage=VacancyStageEnum.FINAL_TEST, shown=True),
            VacancyStageStatus(stage=VacancyStageEnum.OFFER, shown=True),
            VacancyStageStatus(stage=VacancyStageEnum.ACCEPTED, shown=True),
        ]

        final_stages = []

        for stage in stages:
            if is_present[stage.stage]:
                continue  # skip duplicates

            is_present[stage.stage] = True
            final_stages.append(stage)

        for status in default:
            if not is_present[status.stage]:
                final_stages.append(status)

        return final_stages

    class AddVacancyPublicationRequest(BaseModel):
        user_id: UserID
        vacancy_id: VacancyID
        source: Oauth2SourceEnum
        vacancy_url: HttpUrl

    @span(op="vacancy_service", name="add_vacancy_publication")
    async def add_vacancy_publication(self, request: AddVacancyPublicationRequest) -> Vacancy:  # noqa: C901
        try:
            if request.source != Oauth2SourceEnum.HH:
                log.error("Source is not supported", source=request.source)
                raise VacancyServiceError("not implemented source")

            ext_vacancy_id = self._vacancy_importer_service.get_vacancy_id(
                VacancyImporterService.GetVacancyIDRequest(url=request.vacancy_url, source="hh")
            )

            try:
                response = await self._hharon_proxy.init_response_collection(
                    request.user_id, request.vacancy_id, ext_vacancy_id.vacancy_id, ["response"]
                )
            except Exception as e:
                log.error("Error initializing response collection", err=e)
                raise VacancyServiceWrongVacancyUrlError("has no access") from e
            else:
                if response.vacancy_id == "":
                    raise VacancyServiceWrongVacancyUrlError("has no access")

            vacancy = await self.read(self.ReadVacancyRequest(id=request.vacancy_id))
            publication = vacancy.publication
            publication.hh = PublicationStatus(
                state=PublicationStatusEnum.PUBLISHED, url=str(request.vacancy_url), publication_id=response.vacancy_id
            )

            vacancy = await self.update(
                self.UpdateVacancyRequest(
                    id=vacancy.id,
                    publication=UpdateValue(publication),
                ),
            )
            return vacancy
        except (
            VacancyServiceInvalidDataError,
            VacancyServiceVacancyNotFoundError,
            VacancyServiceError,
            VacancyServiceWrongVacancyUrlError,
        ) as e:
            raise e
        except (
            OAuth2ServiceOAuth2NotFoundError,
            OAuth2ServiceEmptyTokenError,
        ) as e:
            log.error("failed to retrieve oauth2 token", err=e)
            raise VacancyServiceOAuth2Error("user is not authorized") from e
        except OAuth2ServiceInvalidDataError as e:
            log.error("failed to add vacancy publication due to retrieving token error", err=e)
            raise VacancyServiceInvalidDataError("invalid data") from e
        except VacancyImporterServiceWrongURLFormatError as e:
            log.error("failed to add vacancy publication due to vacancy url validation error", err=e)
            raise VacancyServiceInvalidDataError("invalid data") from e
        except VacancyImporterServiceError as e:
            log.error("failed to get vacancy id from url", err=e)
            raise VacancyServiceError("vacancy importer error") from e
        except OAuth2ServiceError as e:
            log.error("failed to retrieve token", err=e)
            raise VacancyServiceError("oauth2 error") from e
        except Exception as e:
            log.error("failed to add vacancy publication", err=e)
            raise VacancyServiceError("unknown error") from e

    # ===

    def _vacancy_key(self, vacancy_id: VacancyID) -> Key:
        return self._ks.key("id", str(vacancy_id))

    def _project_set_key(self, project_id: ProjectID) -> Key:
        return self._ks.key("project_set", str(project_id))
