import asyncio
from dataclasses import dataclass
from typing import final

import structlog

from hharon.protocols.response_collection import hh_protocol
from hharon.usecases.token.get_tokens import GetTokens, GetTokensError


class GetPreviewError(Exception): ...


class GetPreviewAccessDeniedError(GetPreviewError): ...


log = structlog.stdlib.get_logger("hharon.usecases.GetResponseCollectionPreviewUsecase")


@final
@dataclass(slots=True)
class GetResponseCollectionPreviewUsecase[SessionT]:
    _adapter: hh_protocol.ResponseCollectionPreviewHHApiProtocol
    _get_tokens: GetTokens[SessionT]

    @dataclass
    class GetPreviewRequest:
        hh_vacancy_id: str
        user_id: str

    @dataclass
    class GetPreviewResponseItem:
        id: str
        """ ID коллекции на Headhunter """
        name: str
        """ Название коллекции на Headhunter """
        total: int
        """ Количество кандидатов в коллекции """
        with_updates: int
        """ Количество кандидатов с обновлениями в коллекции """

    @dataclass
    class GetPreviewResponse:
        vacancy_title: str
        """ Название вакансии на Headhunter """
        vacancy_area: str | None
        """ Регион (город) вакансии на Headhunter """
        collections: list["GetResponseCollectionPreviewUsecase.GetPreviewResponseItem"]
        """ Список коллекций и данных о них """
        total: int
        """ Сумма кандидатов в всех коллекциях """

    async def get_preview(self, request: GetPreviewRequest) -> GetPreviewResponse:
        try:
            tokens = await self._get_tokens.get_tokens(GetTokens.GetTokensRequest(user_id=request.user_id))

            negotiations, vacancy = await asyncio.gather(
                self._adapter.get_negotiations(tokens.access_token, request.hh_vacancy_id),
                self._adapter.get_vacancies_vacancy_id(tokens.access_token, request.hh_vacancy_id),
            )

            collections = [
                self.GetPreviewResponseItem(
                    id=collection.id,
                    name=collection.name,
                    total=collection.counters.total or 0 if collection.counters is not None else 0,
                    with_updates=collection.counters.with_updates or 0 if collection.counters is not None else 0,
                )
                for collection in negotiations.collections
            ]

            return self.GetPreviewResponse(
                vacancy_title=vacancy.name,
                vacancy_area=vacancy.area.name if vacancy.area else None,
                collections=collections,
                total=sum(c.total for c in collections),
            )

        except GetTokensError as e:
            log.exception("failed to get tokens for user_id", request=request, err=e)
            raise GetPreviewAccessDeniedError from e
        except hh_protocol.ResponseCollectionPreviewHHApiAccessDeniedError as e:
            log.warning("user id has no access to specified vacancy", request=request, err=e)
            raise GetPreviewAccessDeniedError from e
        except hh_protocol.ResponseCollectionPreviewHHApiNotFoundError as e:
            log.warning("specified vacancy does not exist", request=request, err=e)
            raise GetPreviewAccessDeniedError from e
        except Exception as e:
            log.exception("unexpected error", request=request, err=e)
            raise GetPreviewError from e
