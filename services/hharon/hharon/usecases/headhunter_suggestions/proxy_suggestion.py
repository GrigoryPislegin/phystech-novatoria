from dataclasses import dataclass
from datetime import timedelta
from typing import final

import structlog

from hharon.domain.headhunter_suggestions import Suggestion
from hharon.protocols.cache.protocol import CacheProtocol
from hharon.protocols.hh_suggestions import HHSuggestionsProtocol
from hharon.usecases.headhunter_suggestions.normalize import normalize_for_filter
from hharon_api.v1 import hharon_pb2

log = structlog.stdlib.get_logger("hharon.usecases.ProxyHeadhunterSuggestions")

CACHE_KEY_PREFIX = "hh_suggestions_proxy"
CACHE_TTL = timedelta(hours=3)


class ProxyHeadhunterSuggestionsError(Exception):
    """Error when getting a suggestion."""


@final
@dataclass(slots=True)
class ProxyHeadhunterSuggestions:
    """Returns a single suggestion (id/item_id, text); caches, matches against HH. Raises when no match."""

    _hh_suggestions: HHSuggestionsProtocol
    _cache: CacheProtocol

    @dataclass
    class ProxySuggestionRequest:
        field: hharon_pb2.GetHeadhunterSuggestionsRequest.Field.ValueType
        text: str

        def __post_init__(self) -> None:
            self.text = self.text.strip()

    @dataclass
    class ProxySuggestionResponse:
        suggestions: list[Suggestion]

    async def proxy_suggestion(self, request: ProxySuggestionRequest) -> ProxySuggestionResponse:
        field = request.field
        text = request.text

        if not text:
            raise ProxyHeadhunterSuggestionsError("empty text")

        normalized = normalize_for_filter(text)
        cache_key = f"{CACHE_KEY_PREFIX}:{field}:{normalized}"

        cached = await self._cache.get(cache_key, unmarshal_as=list[Suggestion])
        if cached is not None:
            log.debug("suggestion_cache_hit", field=field, text=text[:50])
            return self.ProxySuggestionResponse(suggestions=cached)

        suggestions = await self._resolve_suggestion(field, normalized)
        await self._cache.set(cache_key, suggestions, ttl=CACHE_TTL)

        return self.ProxySuggestionResponse(suggestions=suggestions)

    async def _resolve_suggestion(
        self, field: hharon_pb2.GetHeadhunterSuggestionsRequest.Field.ValueType, normalized: str
    ) -> list[Suggestion]:
        """Fetch candidates, match, return best HH suggestion or custom fallback."""
        candidates = await self._hh_suggestions.fetch_suggestions(
            HHSuggestionsProtocol.FetchSuggestionsRequest(field=field, text=normalized, limit=10)
        )

        return [Suggestion(item_id=item.id, text=item.text, score=1) for item in candidates]
