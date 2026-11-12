import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import final

import structlog
from html2text import html2text

from hharon.pkg import hhapi
from hharon.protocols.vacancy import protocol as vacancy_protocol
from hharon.usecases.token.get_tokens import GetTokens
from hharon.usecases.vacancy.vacancy_utils import get_address_city as _get_address_city


class GetHeadhunterVacancyError(Exception): ...


class GetHeadhunterVacancyNotFoundError(GetHeadhunterVacancyError): ...


class GetHeadhunterVacancyAccessDeniedError(GetHeadhunterVacancyError): ...


log = structlog.stdlib.get_logger("hharon.usecases.GetHeadhunterVacancyUsecase")


@final
@dataclass(slots=True)
class GetHeadhunterVacancyUsecase[SessionT]:
    _vacancy_adapter: vacancy_protocol.GetVacancyByIDProtocol
    _get_tokens: GetTokens[SessionT]

    @dataclass
    class GetVacancyRequest:
        hh_vacancy_id: str
        user_id: str

    @dataclass
    class GetVacancyResponse:
        title: str
        """ Название вакансии """
        description: str
        """ Описание вакансии """
        professional_roles: list[str]
        """ Профессиональные роли """
        archived: bool
        """ Заархивирована ли вакансия """
        published_at: datetime
        """ Дата публикации вакансии """
        key_skills: list[str]
        """ Требуемые ключевые навыки """
        address_city: str | None
        """ Город вакансии """
        salary_from: int | None
        """ Минимальная зарплата """
        salary_to: int | None
        """ Максимальная зарплата """
        salary_currency: hhapi.CurrencyEnum | None
        """ Валюта зарплаты """
        salary_gross: bool | None
        """ До вычетов налогов """
        employment_form: hhapi.EmploymentFormEnum | None
        """ Форма занятости """
        work_format: list[hhapi.WorkFormatEnum]
        """ Формат работы """
        work_schedule_by_days: list[hhapi.WorkScheduleByDaysEnum]
        """ График работы """
        working_hours: list[hhapi.WorkingHoursEnum]
        """ Часы работы """
        experience: hhapi.ExperienceEnum | None
        """ Требуемый опыт работы """
        internship: bool
        """ Стажировка """

    async def get_vacancy(self, request: GetVacancyRequest) -> GetVacancyResponse:
        access_token = None

        # try loading access token if it exists, left as None if not
        with contextlib.suppress(Exception):
            tokens = await self._get_tokens.get_tokens(GetTokens.GetTokensRequest(user_id=request.user_id))
            access_token = tokens.access_token

        try:
            vacancy = await self._vacancy_adapter.get_vacancy_by_id(
                self._vacancy_adapter.GetVacancyByIDRequest(access_token, request.hh_vacancy_id)
            )

            return self.GetVacancyResponse(
                title=vacancy.name,
                description=html2text(vacancy.description),
                professional_roles=[role.name for role in vacancy.professional_roles if role.name],
                archived=vacancy.archived,
                published_at=datetime.strptime(vacancy.published_at, "%Y-%m-%dT%H:%M:%S%z").astimezone(UTC),
                key_skills=[skill.name for skill in vacancy.key_skills if skill.name],
                address_city=_get_address_city(vacancy),
                salary_from=vacancy.salary.from_ if vacancy.salary else None,
                salary_to=vacancy.salary.to if vacancy.salary else None,
                salary_currency=hhapi.CurrencyEnum(vacancy.salary.currency)
                if vacancy.salary and vacancy.salary.currency
                else None,
                salary_gross=vacancy.salary.gross if vacancy.salary else None,
                employment_form=hhapi.EmploymentFormEnum(vacancy.employment_form.id)
                if vacancy.employment_form and vacancy.employment_form.id
                else None,
                work_format=[hhapi.WorkFormatEnum(wf.id) for wf in (vacancy.work_format or []) if wf.id],
                work_schedule_by_days=[
                    hhapi.WorkScheduleByDaysEnum(ws.id) for ws in (vacancy.work_schedule_by_days or []) if ws.id
                ],
                working_hours=[hhapi.WorkingHoursEnum(wh.id) for wh in (vacancy.working_hours or []) if wh.id],
                experience=hhapi.ExperienceEnum(vacancy.experience.id)
                if vacancy.experience and vacancy.experience.id
                else None,
                internship=vacancy.internship if vacancy.internship is not None else False,
            )

        except vacancy_protocol.GetVacancyByIDAccessDeniedError as e:
            log.warning("access denied to vacancy", request=request, err=e)
            raise GetHeadhunterVacancyAccessDeniedError from e
        except vacancy_protocol.GetVacancyByIDError as e:
            log.exception("failed to import vacancy from headhunter", request=request, err=e)
            raise GetHeadhunterVacancyNotFoundError from e
        except Exception as e:
            log.exception("unexpected error", request=request, err=e)
            raise GetHeadhunterVacancyError from e
