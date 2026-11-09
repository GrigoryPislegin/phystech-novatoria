from unittest.mock import AsyncMock, Mock

import pytest

from hharon.domain.headhunter_suggestions import Suggestion, SuggestionItem
from hharon.protocols.cache.protocol import CacheProtocol
from hharon.protocols.hh_suggestions import HHSuggestionsProtocol
from hharon.usecases.headhunter_suggestions import (
    GetHeadhunterSuggestions,
    GetHeadhunterSuggestionsError,
)
from hharon_api.v1 import hharon_pb2


@pytest.fixture
def mock_cache() -> Mock:
    cache = Mock(spec=CacheProtocol)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=None)
    return cache


@pytest.fixture
def mock_hh_suggestions() -> Mock:
    return Mock(spec=HHSuggestionsProtocol)


@pytest.fixture
def usecase(mock_cache: Mock, mock_hh_suggestions: Mock) -> GetHeadhunterSuggestions:
    return GetHeadhunterSuggestions(hh_suggestions=mock_hh_suggestions, cache=mock_cache)


# --- Empty text → custom ---


async def test_get_suggestion_empty_text_returns_custom(
    usecase: GetHeadhunterSuggestions, mock_cache: Mock, mock_hh_suggestions: Mock
) -> None:
    """Пустой текст возвращает custom suggestion без вызова кэша и HH."""
    req = GetHeadhunterSuggestions.GetSuggestionRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL, text="   ", limit=10
    )
    resp = await usecase.get_suggestion(req)

    assert resp.suggestion.is_custom
    assert resp.suggestion.item_id.startswith("custom:")
    assert resp.suggestion.text == ""
    assert resp.suggestion.score == 0.0
    assert resp.suggestion.id.startswith("custom:")
    mock_cache.get.assert_not_called()
    mock_hh_suggestions.fetch_suggestions.assert_not_called()


# --- Cache hit ---


async def test_get_suggestion_cache_hit_returns_cached(
    usecase: GetHeadhunterSuggestions, mock_cache: Mock, mock_hh_suggestions: Mock
) -> None:
    """При попадании в кэш возвращается закэшированная suggestion, HH не вызывается."""
    cached = Suggestion(item_id="1114", text="Python", score=0.95)
    mock_cache.get = AsyncMock(return_value=cached)

    req = GetHeadhunterSuggestions.GetSuggestionRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL, text="Python", limit=5
    )
    resp = await usecase.get_suggestion(req)

    assert resp.suggestion is cached
    assert resp.suggestion.id == "1114"
    mock_hh_suggestions.fetch_suggestions.assert_not_called()
    mock_cache.set.assert_not_called()


# --- Cache miss + HH match ---


async def test_get_suggestion_cache_miss_hh_match_returns_hh_suggestion(
    usecase: GetHeadhunterSuggestions, mock_cache: Mock, mock_hh_suggestions: Mock
) -> None:
    """On cache miss and successful HH match returns HH suggestion and caches result."""
    mock_cache.get = AsyncMock(return_value=None)
    mock_hh_suggestions.fetch_suggestions = AsyncMock(
        return_value=[SuggestionItem(id="1114", name="Python", text="Python")]
    )

    req = GetHeadhunterSuggestions.GetSuggestionRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL, text="Python", limit=5
    )
    resp = await usecase.get_suggestion(req)

    assert not resp.suggestion.is_custom
    assert resp.suggestion.item_id == "1114"
    assert resp.suggestion.text == "Python"
    assert resp.suggestion.id == "1114"
    assert resp.suggestion.score >= 0.8
    mock_cache.set.assert_awaited_once()
    call_args = mock_cache.set.call_args
    assert call_args[0][0].startswith("hh_suggestions:1:")
    assert call_args[1]["ttl"] is not None


# --- Cache miss + no match → raise ---


async def test_get_suggestion_cache_miss_no_match_raises(
    usecase: GetHeadhunterSuggestions, mock_cache: Mock, mock_hh_suggestions: Mock
) -> None:
    """При промахе кэша и отсутствии матча — raise; результат кладётся в no_match кэш."""
    mock_cache.get = AsyncMock(return_value=None)
    mock_hh_suggestions.fetch_suggestions = AsyncMock(return_value=[])

    req = GetHeadhunterSuggestions.GetSuggestionRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_METRO, text="НесуществующаяСтанция", limit=5
    )
    with pytest.raises(GetHeadhunterSuggestionsError, match="No matching HH suggestion"):
        await usecase.get_suggestion(req)

    mock_cache.set.assert_called_once()
    call_key = mock_cache.set.call_args[0][0]
    assert "no_match" in call_key
    assert "2:" in call_key


# --- No match cached: повторный запрос не дергает HH ---


async def test_get_suggestion_no_match_cached_second_request_raises_without_hh(
    usecase: GetHeadhunterSuggestions, mock_cache: Mock, mock_hh_suggestions: Mock
) -> None:
    """После no_match результат кэшируется; повторный запрос с тем же текстом кидает ошибку из кэша без вызова HH."""
    mock_cache.get = AsyncMock(return_value=None)
    mock_hh_suggestions.fetch_suggestions = AsyncMock(return_value=[])

    req = GetHeadhunterSuggestions.GetSuggestionRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL, text="XyzNonexistent", limit=5
    )
    with pytest.raises(GetHeadhunterSuggestionsError):
        await usecase.get_suggestion(req)

    hh_calls_after_first = mock_hh_suggestions.fetch_suggestions.await_count
    mock_cache.set.assert_called_once()

    # Второй запрос: success cache пустой, no_match в кэше — raise без HH
    mock_cache.get = AsyncMock(side_effect=[None, b"1"])
    with pytest.raises(GetHeadhunterSuggestionsError):
        await usecase.get_suggestion(req)
    assert mock_hh_suggestions.fetch_suggestions.await_count == hh_calls_after_first


# --- No match raises ---


async def test_get_suggestion_no_match_raises(usecase: GetHeadhunterSuggestions, mock_hh_suggestions: Mock) -> None:
    """При отсутствии кандидатов от HH кидается GetHeadhunterSuggestionsError."""
    mock_hh_suggestions.fetch_suggestions = AsyncMock(return_value=[])

    req = GetHeadhunterSuggestions.GetSuggestionRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL, text="MySkill", limit=5
    )
    with pytest.raises(GetHeadhunterSuggestionsError, match="No matching HH suggestion"):
        await usecase.get_suggestion(req)


# --- Same text reuses suggestion ---


async def test_get_suggestion_same_empty_text_returns_same_custom(
    usecase: GetHeadhunterSuggestions,
) -> None:
    """Two requests with empty text return the same custom suggestion (reuse by key)."""
    req = GetHeadhunterSuggestions.GetSuggestionRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_CITIZENSHIP, text="", limit=1
    )
    r1 = await usecase.get_suggestion(req)
    r2 = await usecase.get_suggestion(req)

    assert r1.suggestion is r2.suggestion
    assert r1.suggestion.id == r2.suggestion.id


# --- Request text is stripped ---


async def test_get_suggestion_strips_request_text(
    usecase: GetHeadhunterSuggestions, mock_cache: Mock, mock_hh_suggestions: Mock
) -> None:
    """Текст в запросе обрезается по краям (GetSuggestionRequest). При отсутствии матча — raise."""
    mock_cache.get = AsyncMock(return_value=None)
    mock_hh_suggestions.fetch_suggestions = AsyncMock(return_value=[])

    req = GetHeadhunterSuggestions.GetSuggestionRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL, text="  Python  ", limit=5
    )
    with pytest.raises(GetHeadhunterSuggestionsError):
        await usecase.get_suggestion(req)

    req2 = GetHeadhunterSuggestions.GetSuggestionRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL, text="  x  ", limit=1
    )
    assert req2.text == "x"


async def test_get_suggestion_cache_key_uses_normalized_text(
    usecase: GetHeadhunterSuggestions, mock_cache: Mock, mock_hh_suggestions: Mock
) -> None:
    """При отсутствии матча в кэш пишется no_match по ключу с normalized; повторный запрос не дергает HH."""
    mock_cache.get = AsyncMock(return_value=None)
    mock_hh_suggestions.fetch_suggestions = AsyncMock(return_value=[])

    req = GetHeadhunterSuggestions.GetSuggestionRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL, text="  пайтон  ", limit=5
    )
    with pytest.raises(GetHeadhunterSuggestionsError):
        await usecase.get_suggestion(req)

    mock_cache.set.assert_called_once()
    no_match_key = mock_cache.set.call_args[0][0]
    assert "no_match" in no_match_key
    assert "1:" in no_match_key

    # Повторный запрос с тем же normalized — ответ из кэша no_match, HH не вызывается
    hh_calls_after_first = mock_hh_suggestions.fetch_suggestions.await_count
    mock_cache.get = AsyncMock(side_effect=[None, b"1"])  # success cache miss, no_match hit
    with pytest.raises(GetHeadhunterSuggestionsError):
        await usecase.get_suggestion(req)
    assert mock_hh_suggestions.fetch_suggestions.await_count == hh_calls_after_first
