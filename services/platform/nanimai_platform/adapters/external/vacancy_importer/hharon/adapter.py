from typing import Final, final, override
from urllib.parse import ParseResult, urlparse

import structlog
from pydantic_extra_types.currency_code import ISO4217 as CurrencyISO4217

from nanimai_platform.domain import (
    ExperienceEnum,
    SalaryAmountRange,
    ScheduleEnum,
    Skill,
    VacancyStatus,
    WorkFormatEnum,
    WorkTypeEnum,
)
from nanimai_platform.external_clients.hharon.hharon_api.v1 import (
    Currency,
    EmploymentForm,
    Experience,
    GetHeadhunterVacancyRequest,
    GetHeadhunterVacancyResponse,
    HharonServiceStub,
    WorkFormat,
    WorkScheduleByDays,
    WorkingHours,
)
from nanimai_platform.protocols.external.vacancy_importer import (
    VacancyImporterError,
    VacancyImporterProtocol,
    WrongURLFormatError,
)

log = structlog.stdlib.get_logger("app.adapters.HHaronVacancyImporterAdapter")

_ALLOWED_SCHEMES: Final[list[str]] = ["http", "https"]
_ALLOWED_NETLOCS: Final[list[str]] = [
    "hh.ru",
    "rabota.by",
    "hh1.az",
    "hh.uz",
    "hh.kz",
    "headhunter.ge",
    "headhunter.kg",
]


@final
class HHaronVacancyImporterAdapter(VacancyImporterProtocol):
    def __init__(self, stub: HharonServiceStub) -> None:
        self._stub = stub

    @override
    async def import_vacancy(
        self, request: VacancyImporterProtocol.ImportVacancyRequest
    ) -> VacancyImporterProtocol.ImportVacancyResponse:
        try:
            response = await self._stub.get_headhunter_vacancy(
                GetHeadhunterVacancyRequest(
                    hh_vacancy_id=self.get_vacancy_id(
                        VacancyImporterProtocol.GetVacancyIDRequest(url=request.url)
                    ).vacancy_id,
                    user_id=str(request.user_id or ""),
                )
            )

            return self._map_vacancy_data_to_response(response)
        except WrongURLFormatError as e:
            log.error("wrong url format", err=e)
            raise e
        except VacancyImporterError as e:
            log.error("failed to import vacancy", err=e)
            raise e
        except Exception as e:
            log.error("failed to import vacancy", err=e)
            raise VacancyImporterError("Unexpected error") from e

    @staticmethod
    def _is_allowed_netloc(netloc: str) -> bool:
        return any(netloc == base or netloc.endswith(f".{base}") for base in _ALLOWED_NETLOCS)

    @override
    def get_vacancy_id(
        self, request: VacancyImporterProtocol.GetVacancyIDRequest
    ) -> VacancyImporterProtocol.GetVacancyIDResponse:
        try:
            parsed: ParseResult = urlparse(str(request.url))

            scheme = parsed.scheme or ""
            netloc = parsed.netloc or ""
            path = parsed.path or ""

            if scheme not in _ALLOWED_SCHEMES:
                raise WrongURLFormatError(f"Must be one of {_ALLOWED_SCHEMES}")
            if not self._is_allowed_netloc(netloc):
                raise WrongURLFormatError(f"Must be one of {_ALLOWED_NETLOCS}")
            if not path or not (path.startswith("/vacancy/") or path.startswith("/vacancies/")):
                raise WrongURLFormatError("It is not link on vacancy")
            parts = [p for p in path.split("/") if p]
            if len(parts) < 2:
                raise WrongURLFormatError("Vacancy ID is missing in link")
            return VacancyImporterProtocol.GetVacancyIDResponse(vacancy_id=str(parts[1]))
        except WrongURLFormatError as e:
            raise e
        except ValueError as e:
            raise WrongURLFormatError("Vacancy id contains not only digits") from e
        except Exception as e:
            raise VacancyImporterError("Unexpected error") from e

    @staticmethod
    def _map_vacancy_data_to_response(
        response: GetHeadhunterVacancyResponse,
    ) -> VacancyImporterProtocol.ImportVacancyResponse:
        """Map HHaron API response to VacancyImporter protocol response."""
        status = VacancyStatus.ARCHIVED if response.archived else VacancyStatus.OPEN
        specialization = response.professional_roles[0] if response.professional_roles else ""

        salary = None
        if response.salary_from is not None or response.salary_to is not None:
            currency_rename = {Currency.RUR: "RUB"}
            currency = (
                currency_rename.get(response.salary_currency, response.salary_currency.name)
                if response.salary_currency
                else "RUB"
            )
            salary = SalaryAmountRange(
                currency=CurrencyISO4217(currency),
                min=response.salary_from,
                max=response.salary_to,
            )

        work_type_map = {
            EmploymentForm.FULL: WorkTypeEnum.FULL_TIME,
            EmploymentForm.PART: WorkTypeEnum.PART_TIME,
            EmploymentForm.PROJECT: WorkTypeEnum.PROJECT,
            EmploymentForm.FLY_IN_FLY_OUT: WorkTypeEnum.SHIFT,
            EmploymentForm.SIDE_JOB: WorkTypeEnum.PART_TIME,
        }
        work_type = (
            work_type_map.get(response.employment_form, WorkTypeEnum.FULL_TIME)
            if response.employment_form
            else WorkTypeEnum.FULL_TIME
        )

        work_format_map = {
            WorkFormat.ON_SITE: WorkFormatEnum.OFFICE,
            WorkFormat.REMOTE: WorkFormatEnum.REMOTE,
            WorkFormat.HYBRID: WorkFormatEnum.HYBRID,
            WorkFormat.FIELD_WORK: WorkFormatEnum.TRAVEL,
        }
        work_format = [work_format_map[wf] for wf in response.work_format if wf in work_format_map]
        if not work_format:
            work_format = [WorkFormatEnum.OFFICE]

        schedule_map = {
            WorkScheduleByDays.SIX_ON_ONE_OFF: ScheduleEnum.SCHEDULE_6_1,
            WorkScheduleByDays.FIVE_ON_TWO_OFF: ScheduleEnum.SCHEDULE_5_2,
            WorkScheduleByDays.FOUR_ON_THREE_OFF: ScheduleEnum.SCHEDULE_4_3,
            WorkScheduleByDays.THREE_ON_THREE_OFF: ScheduleEnum.SCHEDULE_3_3,
            WorkScheduleByDays.THREE_ON_TWO_OFF: ScheduleEnum.SCHEDULE_3_2,
            WorkScheduleByDays.TWO_ON_TWO_OFF: ScheduleEnum.SCHEDULE_2_2,
            WorkScheduleByDays.TWO_ON_ONE_OFF: ScheduleEnum.SCHEDULE_2_1,
        }
        schedule = [schedule_map[s] for s in response.work_schedule_by_days if s in schedule_map]

        daily_rate_map = {
            WorkingHours.HOURS_2: 2,
            WorkingHours.HOURS_3: 3,
            WorkingHours.HOURS_4: 4,
            WorkingHours.HOURS_5: 5,
            WorkingHours.HOURS_6: 6,
            WorkingHours.HOURS_7: 7,
            WorkingHours.HOURS_8: 8,
            WorkingHours.HOURS_9: 9,
            WorkingHours.HOURS_10: 10,
            WorkingHours.HOURS_11: 11,
            WorkingHours.HOURS_12: 12,
            WorkingHours.HOURS_24: 24,
        }
        daily_rate = [daily_rate_map[h] for h in response.working_hours if h in daily_rate_map]

        experience_map = {
            Experience.NOEXPERIENCE: ExperienceEnum.EXP_0,
            Experience.BETWEEN1AND3: ExperienceEnum.EXP_1_3,
            Experience.BETWEEN3AND6: ExperienceEnum.EXP_3_6,
            Experience.MORETHAN6: ExperienceEnum.EXP_6_PLUS,
        }
        experience = (
            experience_map.get(response.experience, ExperienceEnum.EXP_0)
            if response.experience
            else ExperienceEnum.EXP_0
        )

        skills = [Skill(title=skill) for skill in response.key_skills]

        is_temphire = response.employment_form == EmploymentForm.FLY_IN_FLY_OUT if response.employment_form else False

        published_at = response.published_at if response.published_at else None
        if published_at is None:
            raise VacancyImporterError("Published date is required but not provided")

        return VacancyImporterProtocol.ImportVacancyResponse(
            title=response.title,
            description=response.description,
            specialization=specialization,
            status=status,
            city=response.address_city,
            country=None,  # no data
            hire_amount=None,  # no data
            salary=salary,
            work_type=work_type,
            work_format=work_format,
            is_internship=response.internship,
            is_temphire=is_temphire,
            schedule=schedule,
            daily_rate=daily_rate,
            experience=experience,
            skills=skills,
            published_at=published_at,
        )
