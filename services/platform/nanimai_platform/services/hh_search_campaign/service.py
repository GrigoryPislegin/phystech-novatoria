from __future__ import annotations

from typing import final

import structlog
from pydantic import BaseModel

import nanimai_platform.external_clients.hharon.hharon_api.v1 as hharon_api
from nanimai_platform.domain import UserID, VacancyID
from nanimai_platform.domain.vacancy.vacancy import ExperienceEnum, ScheduleEnum, WorkTypeEnum
from nanimai_platform.services.user_profile.service import UserService
from nanimai_platform.services.vacancy.service import VacancyService, VacancyServiceVacancyNotFoundError
from nanimai_platform.utils.logging_span import span
from nanimai_platform.utils.map_grpc_error import AdvancedGRPCError

log = structlog.stdlib.get_logger("app.service.HHSearchCampaignService")


def _map_work_type_to_employment(work_type: WorkTypeEnum) -> list[hharon_api.Employment]:
    """Map vacancy work type to HH employment types."""
    mapping = {
        WorkTypeEnum.FULL_TIME: [hharon_api.Employment.FULL],
        WorkTypeEnum.PART_TIME: [hharon_api.Employment.PART],
        WorkTypeEnum.PROJECT: [hharon_api.Employment.PROJECT],
        WorkTypeEnum.SHIFT: [hharon_api.Employment.FULL],
    }
    return mapping.get(work_type, [])


def _map_experience_to_hh(experience: ExperienceEnum) -> list[hharon_api.Experience]:
    """Map vacancy experience to HH experience."""
    mapping = {
        ExperienceEnum.EXP_0: [hharon_api.Experience.NOEXPERIENCE],
        ExperienceEnum.EXP_1_3: [hharon_api.Experience.BETWEEN1AND3],
        ExperienceEnum.EXP_3_6: [hharon_api.Experience.BETWEEN3AND6],
        ExperienceEnum.EXP_6_PLUS: [hharon_api.Experience.MORETHAN6],
    }
    return mapping.get(experience, [])


def _map_schedule_to_hh(schedule: list[ScheduleEnum]) -> list[hharon_api.Schedule]:
    """Map vacancy schedule to HH schedule."""
    hh_schedules: list[hharon_api.Schedule] = []
    for sched in schedule:
        # Map shift-based schedules to SHIFT
        if sched in [
            ScheduleEnum.SCHEDULE_6_1,
            ScheduleEnum.SCHEDULE_5_2,
            ScheduleEnum.SCHEDULE_4_3,
            ScheduleEnum.SCHEDULE_3_3,
            ScheduleEnum.SCHEDULE_3_2,
            ScheduleEnum.SCHEDULE_2_2,
            ScheduleEnum.SCHEDULE_2_1,
            ScheduleEnum.SCHEDULE_1_1,
        ]:
            if hharon_api.Schedule.SHIFT not in hh_schedules:
                hh_schedules.append(hharon_api.Schedule.SHIFT)

    # If no schedules mapped, default to FULLDAY
    if not hh_schedules:
        hh_schedules.append(hharon_api.Schedule.FULLDAY)

    return hh_schedules


def _map_currency_to_hh(currency_code: str) -> hharon_api.Currency:
    """Map ISO 4217 currency code to HH currency enum."""
    mapping = {
        "AZN": hharon_api.Currency.AZN,
        "BYR": hharon_api.Currency.BYR,
        "EUR": hharon_api.Currency.EUR,
        "GEL": hharon_api.Currency.GEL,
        "KGS": hharon_api.Currency.KGS,
        "KZT": hharon_api.Currency.KZT,
        "RUB": hharon_api.Currency.RUR,
        "UAH": hharon_api.Currency.UAH,
        "USD": hharon_api.Currency.USD,
        "UZS": hharon_api.Currency.UZS,
    }
    return mapping.get(currency_code, hharon_api.Currency.RUR)


class HHSearchCampaignServiceError(Exception): ...


class HHSearchCampaignServiceInvalidDataError(HHSearchCampaignServiceError): ...


class HHSearchCampaignServiceHHaronGRPCError(AdvancedGRPCError): ...


class HHSearchCampaignServiceVacancyNotFoundError(HHSearchCampaignServiceError): ...


class HHSearchCampaignServiceVacancyAccessDeniedError(HHSearchCampaignServiceError): ...


@final
class HHSearchCampaignService:
    def __init__(
        self,
        user_service: UserService,
        vacancy_service: VacancyService,
    ):
        self._user_service = user_service
        self._vacancy_service = vacancy_service

    class GetPrefillFromVacancyRequest(BaseModel):
        user_id: UserID
        vacancy_id: VacancyID

    @span(op="hh_search_campaign_service", name="get_prefill_from_vacancy")
    async def get_prefill_from_vacancy(self, request: GetPrefillFromVacancyRequest) -> hharon_api.SearchCampaign:
        try:
            vacancy = await self._vacancy_service.read(self._vacancy_service.ReadVacancyRequest(id=request.vacancy_id))
        except VacancyServiceVacancyNotFoundError as e:
            log.warning("vacancy not found for prefill", vacancy_id=request.vacancy_id)
            raise HHSearchCampaignServiceVacancyNotFoundError("vacancy not found") from e
        except Exception as e:
            log.exception("failed to read vacancy for prefill", err=e)
            raise HHSearchCampaignServiceError("failed to read vacancy") from e

        if vacancy.user_id != request.user_id:
            log.warning(
                "user has no access to vacancy for prefill",
                vacancy_id=request.vacancy_id,
                user_id=request.user_id,
            )
            raise HHSearchCampaignServiceVacancyAccessDeniedError("no access to vacancy") from None

        campaign = hharon_api.SearchCampaign()

        campaign.employment = _map_work_type_to_employment(vacancy.work_type)
        campaign.experience = _map_experience_to_hh(vacancy.experience)
        campaign.schedule = _map_schedule_to_hh(vacancy.schedule)

        if vacancy.salary and (vacancy.salary.min or vacancy.salary.max):
            salary_filter = hharon_api.SearchCampaignSalaryFilter(
                currency=_map_currency_to_hh(str(vacancy.salary.currency)),
            )
            if vacancy.salary.min:
                salary_filter.min = vacancy.salary.min
            if vacancy.salary.max:
                salary_filter.max = vacancy.salary.max
            campaign.salary = salary_filter

        log.info(
            "created search campaign prefill from vacancy",
            vacancy_id=request.vacancy_id,
            user_id=request.user_id,
        )

        return campaign
