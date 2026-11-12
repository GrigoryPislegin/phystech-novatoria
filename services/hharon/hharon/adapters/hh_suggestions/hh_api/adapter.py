import itertools
from collections.abc import Iterator
from typing import Protocol, final, override

import structlog

from hharon.domain.headhunter_suggestions import (
    MetroStationItem,
    SuggestionItem,
)
from hharon.infra.headhunter import HHHTTPError, HeadHunterClient
from hharon.pkg import hhapi
from hharon.protocols.hh_suggestions import HHSuggestionsError, HHSuggestionsProtocol
from hharon.usecases.headhunter_suggestions.normalize import normalize_for_filter
from hharon_api.v1 import hharon_pb2

log = structlog.stdlib.get_logger("hharon.adapters.HHSuggestionsAdapter")

_MetroCity = hhapi.models.MetroMetroItem
_MetroLine = hhapi.models.MetroMetroLineWithStations
_MetroStation = hhapi.models.MetroLineStation


class Fetcher(Protocol):
    async def __call__(self, text: str, limit: int) -> list[SuggestionItem]: ...


@final
class HHSuggestionsAdapter(HHSuggestionsProtocol):
    def __init__(self, client: HeadHunterClient) -> None:
        self._client = client

    async def _fetch_metro(self, text: str, limit: int) -> list[SuggestionItem]:
        # GET /metro возвращает все города и станции; фильтруем по тексту локально
        payload = await self._client.get(
            "/metro",
            response_model=hhapi.models.MetroMetroResponse,
        )
        log.debug("Fetched metro data", payload=payload)
        query_lower = normalize_for_filter(text)

        def iter_stations() -> Iterator[tuple[_MetroCity, _MetroLine, _MetroStation]]:
            for city in payload.root:
                for line in city.lines:
                    for station in line.stations:
                        yield city, line, station

        def station_item(city: _MetroCity, line: _MetroLine, station: _MetroStation) -> MetroStationItem:
            return MetroStationItem(
                id=station.id,
                name=station.name,
                text=station.name,
                line_id=line.id,
                line_name=line.name,
                city_id=city.id,
                city_name=city.name,
            )

        def matching() -> Iterator[MetroStationItem]:
            for city, line, station in iter_stations():
                sl = normalize_for_filter(station.name)
                if query_lower in sl or sl in query_lower:
                    yield station_item(city, line, station)

        return [
            SuggestionItem(id=item.id, name=item.name, text=item.text) for item in itertools.islice(matching(), limit)
        ]

    async def _fetch_skill_set(self, text: str, limit: int) -> list[SuggestionItem]:
        payload = await self._client.get(
            "/suggests/skill_set",
            params=hhapi.models.SuggestsSkillSetGetParameters(text=text),
            response_model=hhapi.models.SuggestsSkillSet,
        )
        log.debug("Fetched skill set data", payload=payload)

        return [SuggestionItem(id=item.id, name=item.text, text=item.text) for item in payload.items or []][:limit]

    async def _fetch_professional_roles(self, text: str, limit: int) -> list[SuggestionItem]:
        payload = await self._client.get(
            "/suggests/professional_roles",
            params=hhapi.models.SuggestsProfessionalRolesGetParameters(text=text),
            response_model=hhapi.models.SuggestsProfessionalRoles,
        )
        log.debug("Fetched professional roles data", payload=payload)

        return [SuggestionItem.from_hh_item(i) for i in payload.items or []][:limit]

    async def _fetch_educational_institutions(self, text: str, limit: int) -> list[SuggestionItem]:
        payload = await self._client.get(
            "/suggests/educational_institutions",
            params=hhapi.models.SuggestsEducationalInstitutionsGetParameters(text=text),
            response_model=hhapi.models.SuggestsEducationalInstitutions,
        )
        log.debug("Fetched educational institutions data", payload=payload)

        return [
            SuggestionItem.from_hh_item(item, acronym=getattr(item, "acronym", None)) for item in payload.items or []
        ][:limit]

    async def _fetch_areas(self, text: str, limit: int) -> list[SuggestionItem]:
        payload = await self._client.get(
            "/suggests/area_leaves",
            params=hhapi.models.SuggestsAreaLeavesGetParameters(text=text),
            response_model=hhapi.models.SuggestsAreas,
        )
        log.debug("Fetched area leaves data", payload=payload)
        items: list[hhapi.models.SuggestsAreasItem] = list(payload.items)[:limit] if payload.items else []
        return [SuggestionItem.from_hh_item(i) for i in items]

    async def _fetch_languages(self, text: str, limit: int) -> list[SuggestionItem]:
        payload = await self._client.get(
            "/languages",
            params=hhapi.models.LanguagesGetParameters(),
            response_model=hhapi.models.DictionariesLangResponse,
        )
        log.debug("Fetched languages data", payload=payload)

        return [
            SuggestionItem(id=lang.id, name=lang.name, text=lang.name)
            for lang in payload.root
            if text.lower() in lang.name.lower()
        ][:limit]

    async def _fetch_districts(self, text: str, limit: int) -> list[SuggestionItem]:
        payload = await self._client.get(
            "/districts",
            params=hhapi.models.DistrictsGetParameters(),
            response_model=hhapi.models.DictionariesDistrictsResponse,
        )
        log.debug("Fetched districts data", payload=payload)

        return [
            SuggestionItem(id=dist.id, name=dist.name, text=dist.name) for dist in payload.root if text in dist.name
        ][:limit]

    async def _fetch_industries(self, text: str, limit: int) -> list[SuggestionItem]:
        payload = await self._client.get(
            "/industries",
            params=hhapi.models.IndustriesGetParameters(),
            response_model=hhapi.models.DictionariesIndustriesResponse,
        )
        log.debug("Fetched industries data", payload=payload)

        items: list[SuggestionItem] = []
        for industry_topic in payload.root:
            items.extend([
                SuggestionItem(id=industry.id, name=industry.name, text=industry.name)
                for industry in industry_topic.industries
                if text.lower() in industry.name.lower()
            ])

        return items[:limit]

    async def _fetch_countries(self, text: str, limit: int) -> list[SuggestionItem]:
        payload = await self._client.get(
            "/areas/countries",
            params=hhapi.models.AreasCountriesGetParameters(),
            response_model=hhapi.models.DictionariesCountriesResponse,
        )
        log.debug("Fetched countries data", payload=payload)

        return [
            SuggestionItem(id=country.id, name=country.name, text=country.name)
            for country in payload.root
            if text.lower() in country.name.lower()
        ][:limit]

    async def _fetch_by_field(
        self, field: hharon_pb2.GetHeadhunterSuggestionsRequest.Field.ValueType, text: str, limit: int
    ) -> list[SuggestionItem]:
        fetcher: Fetcher | None = None
        match field:
            case hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL:
                fetcher = self._fetch_skill_set
            case hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_METRO:
                fetcher = self._fetch_metro
            case hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_AREA:
                fetcher = self._fetch_areas
            case (
                hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_CITIZENSHIP
                | hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_WORK_TICKET
            ):
                fetcher = self._fetch_countries
            case hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_EDUCATIONAL_INSTITUTION:
                fetcher = self._fetch_educational_institutions
            case hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_PROFESSIONAL_ROLE:
                fetcher = self._fetch_professional_roles
            case hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_LANGUAGE:
                fetcher = self._fetch_languages
            case hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_DISTRICT:
                fetcher = self._fetch_districts
            case hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_INDUSTRY:
                fetcher = self._fetch_industries

            case _:
                return []

        return await fetcher(text, limit)

    @override
    async def fetch_suggestions(self, request: HHSuggestionsProtocol.FetchSuggestionsRequest) -> list[SuggestionItem]:
        field = request.field
        text = request.text.strip()
        limit = request.limit
        if not text:
            return []
        try:
            result = await self._fetch_by_field(field, text, limit)
        except HHHTTPError as e:
            if e.status_code in (400, 404):
                log.debug("hh_suggestions_http", field=field, status_code=e.status_code)
                return []
            raise HHSuggestionsError("HH suggestions request failed") from e
        except Exception as e:
            log.exception("hh_suggestions_fetch_failed", field=field, error=str(e))
            raise HHSuggestionsError("HH suggestions request failed") from e
        else:
            return result
