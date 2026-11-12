import zoneinfo
from datetime import date, datetime, timedelta
from typing import Literal, final

import structlog
from pydantic import BaseModel, HttpUrl

from nanimai_platform.domain import UserID
from nanimai_platform.domain.user_profile.user_profile import UserProfile
from nanimai_platform.domain.vacancy.vacancy import ExperienceEnum, Vacancy
from nanimai_platform.protocols.external.notification.protocol import NotificationProtocol
from nanimai_platform.services.cache.cache import Cache
from nanimai_platform.services.cache.keyspace import Key, Keyspace
from nanimai_platform.services.hharon_proxy import HHaronProxyService
from nanimai_platform.services.oauth2.service import (
    OAuth2ServiceEmptyTokenError,
    OAuth2ServiceError,
    OAuth2ServiceInvalidDataError,
    OAuth2ServiceOAuth2NotFoundError,
)
from nanimai_platform.services.vacancy_importer.service import (
    VacancyImporterService,
    VacancyImporterServiceError,
    VacancyImporterServiceWrongURLFormatError,
)
from nanimai_platform.utils.asyncio_background import launch_background
from nanimai_platform.utils.logging_span import span

log = structlog.stdlib.get_logger("app.service.publisher")


class PublisherServiceError(Exception): ...


class PublisherServiceWrongVacancyUrlError(Exception): ...


class PublisherServiceOAuth2Error(Exception): ...


class PublisherServiceInvalidDataError(Exception): ...


@final
class PublisherService:
    def __init__(
        self,
        notifications: NotificationProtocol,
        cache: Cache,
        vacancy_importer_service: VacancyImporterService,
        hharon_proxy: HHaronProxyService,
    ):
        self._cache = cache
        self._ks = Keyspace("publisher_service")
        self._hharon_proxy = hharon_proxy

        self._notifications = notifications
        self._vacancy_importer_service = vacancy_importer_service

    @span(op="publisher_service", name="publish_vacancy")
    async def publish_vacancy(self, where: str, user: UserProfile, vacancy: Vacancy) -> None:
        try:
            message = f"""
Пользователь {user.name} ({user.email}) запросил публикацию вакансии на плаформе {where}.

Техническая информация:
DT: {datetime.now(zoneinfo.ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M:%S")}
UID: <{str(vacancy.user_id)}>
PID: <{str(vacancy.project_id)}>
VID: <{str(vacancy.id)}>

Вакансия:
Название: {vacancy.title}
Специализация: {vacancy.specialization}
Город: {vacancy.city or "Не указано"}
Страна: {vacancy.country or "Не указано"}
Количество сотрудников: {vacancy.hire_amount or "Не указано"}
Зарплата: {
                (
                    (f"от {vacancy.salary.min} " if vacancy.salary.min is not None else "")
                    + (f"до {vacancy.salary.max}" if vacancy.salary.max is not None else "")
                )
                if vacancy.salary is not None
                else "Не указано"
            }
Вид работы: {vacancy.work_type.value}
Формат работы: {[f.value for f in vacancy.work_format]}
Требуемый опыт: {vacancy.experience.value + " лет" if vacancy.experience != ExperienceEnum.EXP_0 else "не требуется"}
Является стажировкой: {"да" if vacancy.is_internship else "нет"}
Является временной работой: {"да" if vacancy.is_temphire else "нет"}
Рабочие часы: {", ".join(v.value for v in vacancy.schedule)}
Ключевые навыки: {", ".join(v.title for v in vacancy.skills)}

Описание:
{vacancy.description}
"""
            await self._notifications.push(message)

        except Exception as e:
            log.error("failed to publish vacancy", vacancy_id=vacancy.id, user_id=user.id, err=e)
            raise PublisherServiceError() from e

    class PreviewVacancyPublicationRequest(BaseModel):
        user_id: UserID
        url: HttpUrl
        source: Literal["hh"]

    class PreviewVacancyPublicationResponse(BaseModel):
        title: str
        count: int
        city: str | None
        published_until: date

    @span(op="publisher_service", name="add_vacancy_publication")
    async def preview_vacancy_publication(  # noqa: C901
        self, request: PreviewVacancyPublicationRequest
    ) -> PreviewVacancyPublicationResponse:
        try:
            if (
                cache_response := await self._cache.get(
                    self._vacancy_url_key(request.url), t=self.PreviewVacancyPublicationResponse
                )
            ) is not None:
                return cache_response

            if request.source != "hh":
                log.error("Source is not supported", source=request.source)  # pyright: ignore[reportUnreachable]
                raise PublisherServiceError("not implemented source")

            ext_api_vacancy_id = self._vacancy_importer_service.get_vacancy_id(
                VacancyImporterService.GetVacancyIDRequest(url=request.url, source=request.source)
            )

            preview = await self._hharon_proxy.get_response_collection_preview(
                request.user_id, ext_api_vacancy_id.vacancy_id
            )
            total = next((c.total for c in preview.collections if c.id == "response"), 0)

            response = self.PreviewVacancyPublicationResponse(
                title=preview.vacancy_title,
                city=preview.vacancy_area,
                count=total,
                published_until=(datetime.now() + timedelta(days=30)).date(),
            )

            @launch_background
            async def update_cache():
                expire = timedelta(hours=3)
                await self._cache.set(self._vacancy_url_key(request.url), response, expire=expire)

            update_cache()

            return response
        except (PublisherServiceError, PublisherServiceWrongVacancyUrlError) as e:
            raise e
        except (
            OAuth2ServiceOAuth2NotFoundError,
            OAuth2ServiceEmptyTokenError,
        ) as e:
            log.error("failed to retrieve oauth2 token", err=e)
            raise PublisherServiceOAuth2Error("user is not authorized") from e
        except OAuth2ServiceInvalidDataError as e:
            log.error("failed to preview vacancy publication due to retrieving token error", err=e)
            raise PublisherServiceInvalidDataError("invalid data") from e
        except VacancyImporterServiceWrongURLFormatError as e:
            log.error("failed to preview vacancy publication due to vacancy url validation error", err=e)
            raise PublisherServiceInvalidDataError("invalid data") from e
        except VacancyImporterServiceError as e:
            log.error("failed to get vacancy id from url", err=e)
            raise PublisherServiceError("vacancy importer error") from e
        except OAuth2ServiceError as e:
            log.error("failed to retrieve token", err=e)
            raise PublisherServiceError("oauth2 error") from e
        except Exception as e:
            log.error("failed to preview vacancy publication", err=e)
            raise PublisherServiceError("unknown error") from e

    # ===

    def _vacancy_url_key(self, url: HttpUrl) -> Key:
        return self._ks.key("vacancy_url", str(url))
