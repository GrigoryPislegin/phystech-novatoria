from __future__ import annotations

import asyncio
from typing import final

import structlog
from pydantic import BaseModel

from nanimai_platform.domain.scalar.scalars import CandidateID, CriterionID, StopFactorID, UserID, VacancyID
from nanimai_platform.domain.skill import Skill
from nanimai_platform.domain.vacancy import (
    ExperienceEnum,
    SalaryAmountRange,
    ScheduleEnum,
    Vacancy,
    VacancyPublication,
    VacancyStageStatus,
    VacancyStatistics,
    VacancyStatus,
    WorkFormatEnum,
    WorkTypeEnum,
)
from nanimai_platform.services.balance.service import (
    BalanceService,
    BalanceServiceError,
    BalanceServiceInvalidDataError,
)
from nanimai_platform.services.criterion.service import (
    CriterionService,
    CriterionServiceCriterionNotFoundError,
    CriterionServiceError,
    CriterionServiceInvalidDataError,
    CriterionServiceVacancyNotFoundError,
)
from nanimai_platform.services.hharon_proxy.service import (
    HHaronProxyService,
    HharonError,
)
from nanimai_platform.services.stop_factor.service import (
    StopFactorService,
    StopFactorServiceError,
    StopFactorServiceInvalidDataError,
    StopFactorServiceStopFactorNotFoundError,
    StopFactorServiceVacancyNotFoundError,
)
from nanimai_platform.services.vacancy.service import (
    VacancyService,
    VacancyServiceError,
    VacancyServiceInvalidDataError,
    VacancyServiceVacancyNotFoundError,
)
from nanimai_platform.utils.logging_span import span
from nanimai_platform.utils.update_value import UpdateValue

log = structlog.stdlib.get_logger("app.service.VacancyRichUpdateHook")


class VacancyRichUpdateHookError(Exception): ...


class VacancyRichUpdateHookHHaronError(Exception): ...


class VacancyRichUpdateHookInvalidDataError(Exception): ...


class VacancyRichUpdateHookVacancyNotFoundError(Exception): ...


class VacancyRichUpdateHookCriterionNotFoundError(Exception): ...


class VacancyRichUpdateHookStopFactorNotFoundError(Exception): ...


@final
class VacancyRichUpdateHook:
    def __init__(
        self,
        vacancy_service: VacancyService,
        criterion_service: CriterionService,
        balance_service: BalanceService,
        stop_factor_service: StopFactorService,
        hharon_proxy_service: HHaronProxyService,
    ):
        self._vacancy_service = vacancy_service
        self._criterion_service = criterion_service
        self._balance_service = balance_service
        self._stop_factor_service = stop_factor_service
        self._hharon_proxy_service = hharon_proxy_service

    class CreateCriterionRequest(BaseModel):
        criterion: str
        initial_weight: int

    class CreateStopFactorRequest(BaseModel):
        stop_factor: str
        initial_weight: int

    class UpdateCriterionRequest(BaseModel):
        id: CriterionID
        initial_weight: int

    class UpdateStopFactorRequest(BaseModel):
        id: StopFactorID
        initial_weight: int

    class RichUpdateVacancyRequest(BaseModel):
        user_id: UserID
        vacancy_id: VacancyID

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

        put_criteria: list[VacancyRichUpdateHook.UpdateCriterionRequest] | None = None
        put_stop_factors: list[VacancyRichUpdateHook.UpdateStopFactorRequest] | None = None
        post_criteria: list[VacancyRichUpdateHook.CreateCriterionRequest] | None = None
        post_stop_factors: list[VacancyRichUpdateHook.CreateStopFactorRequest] | None = None
        limit_maximum: int | None = None

    @span(op="vacancy_rich_update_hook", name="rich_update_vacancy")
    async def rich_update_vacancy(self, request: RichUpdateVacancyRequest) -> Vacancy:  # noqa: C901
        try:
            if request.limit_maximum:
                await self._balance_service.upsert_limit(
                    BalanceService.UpsertLimitRequest(
                        user_id=request.user_id,
                        resource_id=request.vacancy_id,
                        maximum=request.limit_maximum,
                    )
                )

            vacancy = await self._vacancy_service.update(
                VacancyService.UpdateVacancyRequest(
                    id=request.vacancy_id,
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
                )
            )
            if request.status is not None and request.status.value == VacancyStatus.ARCHIVED:
                try:
                    log.info(
                        "Stopping search campaign and response collection for archived vacancy",
                        vacancy_id=request.vacancy_id,
                    )
                    await self._hharon_proxy_service.complete_search_campaign_execution(request.vacancy_id)
                    await self._hharon_proxy_service.complete_response_collection(request.vacancy_id)
                    log.info(
                        "Successfully completed response collection and search campaign execution",
                        vacancy_id=request.vacancy_id,
                    )
                except HharonError as e:
                    log.warning(
                        "Failed to complete response collection and search campaign execution",
                        vacancy_id=request.vacancy_id,
                        err=e,
                    )
                except Exception as e:
                    log.warning(
                        "Unexpected error while completing response collection and search campaign execution",
                        vacancy_id=request.vacancy_id,
                        err=e,
                    )

            if request.put_criteria:
                await asyncio.gather(*[
                    self._criterion_service.update(
                        CriterionService.UpdateCriterionRequest(
                            id=criterion.id,
                            initial_weight=criterion.initial_weight,
                        )
                    )
                    for criterion in request.put_criteria
                ])

            if request.put_stop_factors:
                await asyncio.gather(*[
                    self._stop_factor_service.update(
                        StopFactorService.UpdateStopFactorRequest(
                            id=stop_factor.id,
                            initial_weight=stop_factor.initial_weight,
                        )
                    )
                    for stop_factor in request.put_stop_factors
                ])

            if request.post_criteria:
                await asyncio.gather(*[
                    self._criterion_service.create(
                        CriterionService.CreateCriterionRequest(
                            user_id=request.user_id,
                            project_id=vacancy.project_id,
                            vacancy_id=vacancy.id,
                            criterion=criterion.criterion,
                            initial_weight=criterion.initial_weight,
                        )
                    )
                    for criterion in request.post_criteria
                ])

            if request.post_stop_factors:
                await asyncio.gather(*[
                    self._stop_factor_service.create(
                        StopFactorService.CreateStopFactorRequest(
                            user_id=request.user_id,
                            project_id=vacancy.project_id,
                            vacancy_id=vacancy.id,
                            stop_factor=stop_factor.stop_factor,
                            initial_weight=stop_factor.initial_weight,
                        )
                    )
                    for stop_factor in request.post_stop_factors
                ])

            return vacancy

        except (
            BalanceServiceInvalidDataError,
            VacancyServiceInvalidDataError,
            CriterionServiceInvalidDataError,
            StopFactorServiceInvalidDataError,
        ) as e:
            log.error("failed to update vacancy due to validation error", err=e)
            raise VacancyRichUpdateHookInvalidDataError("invalid data") from e
        except (
            VacancyServiceVacancyNotFoundError,
            CriterionServiceVacancyNotFoundError,
            StopFactorServiceVacancyNotFoundError,
        ) as e:
            log.error("failed to find vacancy", err=e)
            raise VacancyRichUpdateHookVacancyNotFoundError("failed to find") from e
        except HharonError as e:
            log.error("failed to complete response collection and search campaign execution", err=e)
            raise VacancyRichUpdateHookHHaronError(
                "failed to complete response collection and search campaign execution"
            ) from e
        except CriterionServiceCriterionNotFoundError as e:
            log.error("failed to find criterion", err=e)
            raise VacancyRichUpdateHookCriterionNotFoundError("failed to find") from e
        except StopFactorServiceStopFactorNotFoundError as e:
            log.error("failed to find stop-factor", err=e)
            raise VacancyRichUpdateHookStopFactorNotFoundError("failed to find") from e
        except (
            BalanceServiceError,
            VacancyServiceError,
            CriterionServiceError,
            StopFactorServiceError,
        ) as e:
            log.error("failed to update vacancy", err=e)
            raise VacancyRichUpdateHookError("failed to update") from e
        except Exception as e:
            log.error("failed to update vacancy", err=e)
            raise VacancyRichUpdateHookError("unknown error") from e
