from dataclasses import dataclass
from datetime import timedelta
from typing import cast, final
from uuid import uuid4

import structlog

from hharon.domain.headhunter_suggestions import Suggestion
from hharon.protocols.cache.protocol import CacheProtocol
from hharon.protocols.hh_suggestions import HHSuggestionsProtocol
from hharon.usecases.headhunter_suggestions.matching import (
    compute_score,
    select_best_candidate,
    threshold_for,
)
from hharon.usecases.headhunter_suggestions.normalize import normalize_for_matching
from hharon_api.v1 import hharon_pb2

log = structlog.stdlib.get_logger("hharon.usecases.GetHeadhunterSuggestions")

CACHE_KEY_PREFIX = "hh_suggestions"
CACHE_NO_MATCH_PREFIX = "hh_suggestions:no_match"
CACHE_TTL = timedelta(hours=3)


class GetHeadhunterSuggestionsError(Exception):
    """Error when getting a suggestion."""


@final
class GetHeadhunterSuggestions:
    """Returns a single suggestion (id/item_id, text); caches, matches against HH. Raises when no match."""

    def __init__(
        self,
        *,
        hh_suggestions: HHSuggestionsProtocol,
        cache: CacheProtocol,
    ) -> None:
        self._hh_suggestions = hh_suggestions
        self._cache = cache
        self._suggestion_by_key: dict[
            tuple[hharon_pb2.GetHeadhunterSuggestionsRequest.Field.ValueType, str], Suggestion
        ] = {}

    @dataclass
    class GetSuggestionRequest:
        field: hharon_pb2.GetHeadhunterSuggestionsRequest.Field.ValueType
        text: str
        limit: int = 20

        def __post_init__(self) -> None:
            self.text = self.text.strip()

    @dataclass
    class GetSuggestionResponse:
        suggestion: Suggestion

    async def get_suggestion(
        self, request: "GetHeadhunterSuggestions.GetSuggestionRequest"
    ) -> "GetHeadhunterSuggestions.GetSuggestionResponse":
        field = request.field
        text = request.text
        limit = request.limit
        if not text:
            return self.GetSuggestionResponse(suggestion=self._create_custom(field, ""))

        normalized = normalize_for_matching(field, text)
        cache_key = f"{CACHE_KEY_PREFIX}:{field}:{normalized}"
        no_match_key = f"{CACHE_NO_MATCH_PREFIX}:{field}:{normalized}"

        cached = await self._cache.get(cache_key, unmarshal_as=Suggestion)
        if cached is not None:
            log.debug("suggestion_cache_hit", field=field, text=text[:50])
            return self.GetSuggestionResponse(suggestion=cached)

        no_match_cached = await self._cache.get(no_match_key)
        if no_match_cached is not None:
            log.debug("suggestion_no_match_cache_hit", field=field, text=text[:50])
            msg = f"No matching HH suggestion for field={field!r}, text={text[:50]!r}"
            raise GetHeadhunterSuggestionsError(msg)

        try:
            suggestion = await self._resolve_suggestion(field, text, normalized, limit)
        except GetHeadhunterSuggestionsError:
            await self._cache.set(no_match_key, b"1", ttl=CACHE_TTL)
            raise

        await self._cache.set(cache_key, suggestion.model_dump_json().encode(), ttl=CACHE_TTL)
        return self.GetSuggestionResponse(suggestion=suggestion)

    async def _resolve_suggestion(
        self,
        field: hharon_pb2.GetHeadhunterSuggestionsRequest.Field.ValueType,
        text: str,
        normalized: str,
        limit: int,
    ) -> Suggestion:
        """Fetch candidates, match, return best HH suggestion or custom fallback."""
        candidates_with_scores: list[tuple[dict[str, object], float]] = []
        for query in self._query_variants(text, normalized):
            raw = await self._hh_suggestions.fetch_suggestions(
                HHSuggestionsProtocol.FetchSuggestionsRequest(field=field, text=query, limit=limit)
            )
            for item in raw:
                d = item.model_dump()
                candidates_with_scores.append((d, compute_score(field, text, d)))

        best_item, best_score = select_best_candidate(candidates_with_scores)
        if best_item is None or best_score < threshold_for(field):
            log.warning(
                "suggestion_not_found",
                field=field,
                text=text[:50],
                best_score=best_score,
            )
            msg = f"No matching HH suggestion for field={field!r}, text={text[:50]!r}"
            raise GetHeadhunterSuggestionsError(msg)

        suggestion = self._suggestion_from_hh_item(field, best_item, best_score)
        log.info(
            "suggestion_hh_match",
            field=field,
            text=text[:50],
            score=best_score,
            hharon_id=suggestion.id,
            hh_manager_id=suggestion.item_id,
        )
        return suggestion

    def _query_variants(self, original: str, normalized: str) -> list[str]:
        """Query strings for HH (normalized may include translit for skills). Dedupe, preserve order."""
        variants = list(dict.fromkeys(s for s in (normalized, original) if s))
        return cast("list[str]", variants if variants else [original or normalized])  # pyright: ignore[reportUnnecessaryCast]

    def _suggestion_from_hh_item(
        self,
        field: hharon_pb2.GetHeadhunterSuggestionsRequest.Field.ValueType,
        hh_item: dict[str, object],
        score: float,
    ) -> Suggestion:
        """Get or create Suggestion for HH item; reuse by (field, item_id)."""
        label = str(hh_item.get("name", "") or hh_item.get("text", ""))
        item_id = str(hh_item.get("id") or uuid4())
        key = (field, item_id)
        if key in self._suggestion_by_key:
            return self._suggestion_by_key[key]
        suggestion = Suggestion(item_id=item_id, text=label, score=score)
        self._suggestion_by_key[key] = suggestion
        return suggestion

    def _create_custom(
        self, field: hharon_pb2.GetHeadhunterSuggestionsRequest.Field.ValueType, text: str
    ) -> Suggestion:
        """Get or create custom suggestion (no HH id, user input)."""
        key = (field, text)
        if key in self._suggestion_by_key:
            return self._suggestion_by_key[key]
        suggestion = Suggestion(
            item_id=f"custom:{uuid4()}",
            text=text,
            score=0.0,
        )
        self._suggestion_by_key[key] = suggestion
        return suggestion
