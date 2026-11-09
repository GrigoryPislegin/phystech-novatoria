import functools
import traceback
from datetime import UTC, datetime
from typing import Any, Final, final, override
from urllib.parse import ParseResult, urlparse

import httpx
import pydantic
import structlog
from html2text import html2text
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
from nanimai_platform.protocols.external.vacancy_importer import (
    VacancyImporterError,
    VacancyImporterProtocol,
    WrongURLFormatError,
)

log = structlog.stdlib.get_logger("app.adapters.NativeHHVacancyImporterAdapter")

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
class NativeHHVacancyImporterAdapter(VacancyImporterProtocol):
    def __init__(self, user_agent: str) -> None:
        self.user_agent = user_agent
        self._api_client = httpx.AsyncClient(
            headers={"User-Agent": self.user_agent},
            base_url="https://api.hh.ru",
            timeout=30.0,
        )
        self.R = self._api_client.build_request
        self.GET = functools.partial(self.R, "GET")
        self.POST = functools.partial(self.R, "POST")

    @override
    async def import_vacancy(
        self, request: VacancyImporterProtocol.ImportVacancyRequest
    ) -> VacancyImporterProtocol.ImportVacancyResponse:
        try:
            vacancy_id = self.get_vacancy_id(VacancyImporterProtocol.GetVacancyIDRequest(url=request.url))
            return await self.import_vacancy_by_id(vacancy_id.vacancy_id)
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
                raise WrongURLFormatError(f"Must be one of {_ALLOWED_SCHEMES}")
            if not (path or path.startswith("/vacancy/") or path.startswith("/vacancies/")):
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

    async def run(self, request: httpx.Request) -> dict[str, Any]:
        try:
            response = await self._api_client.send(request)
            response.raise_for_status()

            try:
                data = response.json()
                return data
            except Exception as e:
                log.error("failed to decode response", response=response)
                raise VacancyImporterError("Failed to parse JSON response") from e
        except httpx.HTTPStatusError as e:
            r = e.response
            log.error(
                "HTTP error in HH API request",
                status_code=e.response.status_code,
                error=str(e),
                response_text=e.response.text[:500],
            )
            raise VacancyImporterError("HTTP error in HH API", r.status_code, r.text[:500]) from e
        except httpx.RequestError as e:
            log.error(
                "Request error in HH API call",
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )
            raise VacancyImporterError("Request error in HH API") from e
        except Exception as e:
            log.error(
                "Unexpected error in HH API call",
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )
            raise VacancyImporterError("Unexpected error in HH API") from e

    @staticmethod
    def _map_hh_to_iso_currency(currency: str) -> CurrencyISO4217:
        currency_mapping = {
            # Azerbaijani manat
            "AZM": "AZN",
            "AZN": "AZN",
            # Belarusian ruble
            "BYR": "BYN",
            "BYN": "BYN",
            # Euro
            "EUR": "EUR",
            # Georgian lari
            "GEL": "GEL",
            # Kyrgyzstani som
            "KGS": "KGS",
            # Soviet Union ruble
            "SUR": "RUB",
            # Kazakhstani tenge
            "KZT": "KZT",
            # Russian ruble
            "RUR": "RUB",
            "RUB": "RUB",
            # Ukrainian hryvnia
            "UAH": "UAH",
            # Ukrainian karbovanets
            "UAK": "UAK",
            # USD
            "USD": "USD",
            # Uzbekistani sum
            "UZS": "UZS",
        }
        return CurrencyISO4217(currency_mapping.get(currency, "RUB"))

    @staticmethod
    def _map_hh_to_work_type(wt: str) -> WorkTypeEnum:
        work_type_mapping = {
            "FULL": WorkTypeEnum.FULL_TIME,
            "PART": WorkTypeEnum.PART_TIME,
            "PROJECT": WorkTypeEnum.PROJECT,
            "FLY_IN_FLY_OUT": WorkTypeEnum.SHIFT,
        }

        return work_type_mapping.get(wt, WorkTypeEnum.FULL_TIME)

    @staticmethod
    def _map_hh_to_work_format(wf: str) -> WorkFormatEnum | None:
        work_type_mapping = {
            "ON_SITE": WorkFormatEnum.OFFICE,
            "REMOTE": WorkFormatEnum.REMOTE,
            "HYBRID": WorkFormatEnum.HYBRID,
            "FIELD_WORK": WorkFormatEnum.TRAVEL,
        }

        return work_type_mapping.get(wf, None)

    @staticmethod
    def _map_hh_to_work_schedule(ws: str) -> ScheduleEnum | None:
        work_schedule_mapping = {
            "6/1": ScheduleEnum.SCHEDULE_6_1,
            "5/2": ScheduleEnum.SCHEDULE_5_2,
            "4/3": ScheduleEnum.SCHEDULE_4_3,
            "3/3": ScheduleEnum.SCHEDULE_3_3,
            "3/2": ScheduleEnum.SCHEDULE_3_2,
            "2/2": ScheduleEnum.SCHEDULE_2_2,
            "2/1": ScheduleEnum.SCHEDULE_2_1,
            "1/1": ScheduleEnum.SCHEDULE_1_1,
        }

        return work_schedule_mapping.get(ws, None)

    @staticmethod
    def _map_hh_to_daily_rate(dr: str) -> int | None:
        work_dr_mapping = {
            "HOURS_2": 2,
            "HOURS_3": 3,
            "HOURS_4": 4,
            "HOURS_5": 5,
            "HOURS_6": 6,
            "HOURS_7": 7,
            "HOURS_8": 8,
            "HOURS_9": 9,
            "HOURS_10": 10,
            "HOURS_11": 11,
            "HOURS_12": 12,
            "HOURS_24": 24,
        }

        return work_dr_mapping.get(dr, None)

    @staticmethod
    def _map_hh_to_experience(exp: str) -> ExperienceEnum:
        exp_mapping = {
            "noExperience": ExperienceEnum.EXP_0,
            "between1And3": ExperienceEnum.EXP_1_3,
            "between3And6": ExperienceEnum.EXP_3_6,
            "moreThan6": ExperienceEnum.EXP_6_PLUS,
        }

        return exp_mapping.get(exp, ExperienceEnum.EXP_0)

    async def import_vacancy_by_id(self, vacancy_id: str) -> VacancyImporterProtocol.ImportVacancyResponse:
        try:
            r = await self.run(
                self.GET(
                    f"/vacancies/{vacancy_id}",
                )
            )

            title = r.get("name", "")
            description = html2text(r.get("description", ""))
            prof_roles = r.get("professional_roles") or []
            _published_at_raw = r.get("published_at")

            if isinstance(_published_at_raw, str):
                _published_at = datetime.strptime(_published_at_raw, "%Y-%m-%dT%H:%M:%S%z")
                published_at = _published_at.astimezone(UTC)
            else:
                raise VacancyImporterError("failed to get published at from api")

            specialization = prof_roles[0].get("name", "") if prof_roles else ""
            status = VacancyStatus.ARCHIVED if r.get("archived") else VacancyStatus.OPEN
            city = (r.get("address") or {}).get("city") or None
            country = None
            hire_amount = None
            r_salary = r.get("salary", {})
            salary = None
            if r_salary:
                salary = SalaryAmountRange(
                    currency=self._map_hh_to_iso_currency(r_salary.get("currency", "RUB")),  # pyright: ignore[reportArgumentType]
                    min=r_salary.get("from", None),
                    max=r_salary.get("to", None),
                )
            work_type = self._map_hh_to_work_type(r.get("employment_form", {}).get("id", "full-time"))
            work_format = [
                wf for f in r.get("work_format", [{}]) if (wf := self._map_hh_to_work_format(f.get("id"))) is not None
            ]
            is_internship = r.get("internship", False)
            is_temphire = False
            schedule = [
                ws
                for f in r.get("work_schedule_by_days", [])
                if (ws := self._map_hh_to_work_schedule(f.get("name"))) is not None
            ]
            daily_rate = [
                dr for f in r.get("working_hours", []) if (dr := self._map_hh_to_daily_rate(f.get("id"))) is not None
            ]
            experience = self._map_hh_to_experience(r.get("experience", {}).get("id", "NO_EXPERIENCE"))
            skills = [Skill(title=name) for sk in r.get("key_skills", []) if (name := sk.get("name"))]

            return VacancyImporterProtocol.ImportVacancyResponse(
                title=title,
                description=description,
                specialization=specialization,
                status=status,
                city=city,
                country=country,
                hire_amount=hire_amount,
                salary=salary,
                work_type=work_type,
                work_format=work_format,
                is_internship=is_internship,
                is_temphire=is_temphire,
                schedule=schedule,
                daily_rate=daily_rate,
                experience=experience,
                skills=skills,
                published_at=published_at,
            )
        except pydantic.ValidationError as e:
            raise VacancyImporterError("validation error") from e
        except VacancyImporterError as e:
            raise e
        except Exception as e:
            raise VacancyImporterError("Unexpected error in HH API") from e
