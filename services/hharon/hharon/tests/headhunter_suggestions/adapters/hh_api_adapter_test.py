"""Tests for HH suggestions adapter: mocks and integration with real HH API."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, Mock

import pytest

from hharon.adapters.hh_suggestions.hh_api import HHSuggestionsAdapter
from hharon.infra.headhunter import HeadHunterClient, RawHeadHunterClient
from hharon.protocols.hh_suggestions import HHSuggestionsProtocol
from hharon_api.v1 import hharon_pb2


@pytest.fixture
def mock_hh_client() -> Mock:
    return Mock(spec=HeadHunterClient)


@pytest.fixture
def adapter_with_mock(mock_hh_client: Mock) -> HHSuggestionsAdapter:
    return HHSuggestionsAdapter(client=mock_hh_client)  # type: ignore[arg-type]


# --- Mock tests: all SuggestionFieldType branches ---


@pytest.mark.asyncio
async def test_fetch_suggestions_empty_text_returns_empty(
    adapter_with_mock: HHSuggestionsAdapter, mock_hh_client: Mock
) -> None:
    """Empty text returns empty list without calling HH API."""
    req = HHSuggestionsProtocol.FetchSuggestionsRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL, text="   ", limit=5
    )
    result = await adapter_with_mock.fetch_suggestions(req)
    assert result == []
    mock_hh_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_suggestions_skill_mock(adapter_with_mock: HHSuggestionsAdapter, mock_hh_client: Mock) -> None:
    """Mock: SKILL returns candidates from HH skill_set response."""
    mock_hh_client.get = AsyncMock(
        return_value=Mock(
            items=[
                Mock(id="1114", text="Python"),
                Mock(id="674", text="JavaScript"),
            ]
        )
    )
    req = HHSuggestionsProtocol.FetchSuggestionsRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL, text="Python", limit=5
    )
    result = await adapter_with_mock.fetch_suggestions(req)
    assert len(result) == 2
    assert result[0].id == "1114"
    assert result[0].text == "Python"
    mock_hh_client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_suggestions_metro_mock(adapter_with_mock: HHSuggestionsAdapter, mock_hh_client: Mock) -> None:
    """Mock: METRO returns stations filtered by query from /metro response."""
    station = Mock()
    station.id = "6.42"
    station.name = "Kozhukhovskaya"
    line = Mock()
    line.id = "6"
    line.name = "Lyublinsko-Dmitrovskaya"
    line.stations = [station]
    city = Mock()
    city.id = "1"
    city.name = "Moscow"
    city.lines = [line]
    mock_hh_client.get = AsyncMock(return_value=Mock(root=[city]))
    req = HHSuggestionsProtocol.FetchSuggestionsRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_METRO, text="Kozhukhovskaya", limit=10
    )
    result = await adapter_with_mock.fetch_suggestions(req)
    assert len(result) == 1
    assert result[0].id == "6.42"
    assert result[0].text == "Kozhukhovskaya"
    mock_hh_client.get.assert_awaited_once()
    assert mock_hh_client.get.call_args[0][0] == "/metro"


@pytest.mark.asyncio
async def test_fetch_suggestions_professional_role_mock(
    adapter_with_mock: HHSuggestionsAdapter, mock_hh_client: Mock
) -> None:
    """Mock: PROFESSIONAL_ROLE returns candidates from HH professional_roles suggest."""
    mock_hh_client.get = AsyncMock(
        return_value=Mock(
            items=[
                Mock(id="160", text="Developer"),
                Mock(id="165", text="Backend developer"),
            ]
        )
    )
    req = HHSuggestionsProtocol.FetchSuggestionsRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_PROFESSIONAL_ROLE, text="developer", limit=5
    )
    result = await adapter_with_mock.fetch_suggestions(req)
    assert len(result) == 2
    assert result[0].id == "160"
    assert result[0].text == "Developer"
    mock_hh_client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_suggestions_educational_institution_mock(
    adapter_with_mock: HHSuggestionsAdapter, mock_hh_client: Mock
) -> None:
    """Mock: EDUCATIONAL_INSTITUTION returns candidates from HH educational_institutions suggest."""
    mock_hh_client.get = AsyncMock(
        return_value=Mock(
            items=[
                Mock(id="123", text="Moscow State University", acronym="MSU"),
                Mock(id="456", text="Higher School of Economics"),
            ]
        )
    )
    req = HHSuggestionsProtocol.FetchSuggestionsRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_EDUCATIONAL_INSTITUTION, text="MSU", limit=5
    )
    result = await adapter_with_mock.fetch_suggestions(req)
    assert len(result) == 2
    assert result[0].id == "123"
    assert result[0].text == "Moscow State University"
    assert result[0].acronym == "MSU"
    mock_hh_client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_suggestions_citizenship_mock(
    adapter_with_mock: HHSuggestionsAdapter, mock_hh_client: Mock
) -> None:
    """Mock: CITIZENSHIP uses areas/countries and returns countries."""
    russia = Mock()
    russia.id = "113"
    russia.name = "Russia"
    russia.url = "https://api.hh.ru/areas/113"
    kazakhstan = Mock()
    kazakhstan.id = "40"
    kazakhstan.name = "Kazakhstan"
    kazakhstan.url = "https://api.hh.ru/areas/40"
    mock_hh_client.get = AsyncMock(return_value=Mock(root=[russia, kazakhstan]))
    req = HHSuggestionsProtocol.FetchSuggestionsRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_CITIZENSHIP, text="Russia", limit=5
    )
    result = await adapter_with_mock.fetch_suggestions(req)
    assert len(result) == 1
    assert result[0].id == "113"
    assert result[0].name == "Russia"
    assert result[0].text == "Russia"
    mock_hh_client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_suggestions_work_ticket_mock(
    adapter_with_mock: HHSuggestionsAdapter, mock_hh_client: Mock
) -> None:
    """Mock: WORK_TICKET uses areas/countries (same as CITIZENSHIP) and returns countries."""
    russia = Mock()
    russia.id = "113"
    russia.name = "Russia"
    russia.url = "https://api.hh.ru/areas/113"
    kazakhstan = Mock()
    kazakhstan.id = "40"
    kazakhstan.name = "Kazakhstan"
    kazakhstan.url = "https://api.hh.ru/areas/40"
    mock_hh_client.get = AsyncMock(return_value=Mock(root=[russia, kazakhstan]))
    req = HHSuggestionsProtocol.FetchSuggestionsRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_WORK_TICKET, text="Russia", limit=5
    )
    result = await adapter_with_mock.fetch_suggestions(req)
    assert len(result) == 1
    assert result[0].id == "113"
    assert result[0].name == "Russia"
    assert result[0].text == "Russia"
    mock_hh_client.get.assert_awaited_once()


# --- Integration tests: real requests to api.hh.ru ---


@pytest.fixture
async def real_hh_client() -> AsyncGenerator[HeadHunterClient]:
    """Real HTTP client to HH API (for integration tests)."""
    client = RawHeadHunterClient(
        base_url="https://api.hh.ru",
        headers={"User-Agent": "hharon-tests/1.0"},
        timeout=15.0,
    )
    try:
        yield HeadHunterClient(client)
    finally:
        await client.aclose()


@pytest.fixture
def real_adapter(real_hh_client: HeadHunterClient) -> HHSuggestionsAdapter:
    return HHSuggestionsAdapter(client=real_hh_client)


@pytest.mark.asyncio
@pytest.mark.real_api
async def test_fetch_suggestions_skill_real_api(real_adapter: HHSuggestionsAdapter) -> None:
    """Integration: fetch skill suggestions for 'Python' from HH API."""
    req = HHSuggestionsProtocol.FetchSuggestionsRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL, text="Python", limit=10
    )
    candidates = await real_adapter.fetch_suggestions(req)
    assert len(candidates) > 0
    texts: list[str] = [c.text or c.name for c in candidates]
    assert any("python" in t.lower() for t in texts), f"Expected Python in {texts}"


@pytest.mark.asyncio
@pytest.mark.real_api
async def test_fetch_suggestions_metro_real_api(real_adapter: HHSuggestionsAdapter) -> None:
    """Integration: fetch metro stations for 'Kozhukhovskaya' (filtered from /metro)."""
    req = HHSuggestionsProtocol.FetchSuggestionsRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_METRO, text="Кожуховская", limit=10
    )
    candidates = await real_adapter.fetch_suggestions(req)
    assert len(candidates) > 0
    texts = [c.text or c.name for c in candidates]
    assert any("кожуховская" in t.lower() for t in texts), f"Expected Кожуховская in {texts}"


@pytest.mark.asyncio
@pytest.mark.real_api
async def test_fetch_suggestions_citizenship_real_api(real_adapter: HHSuggestionsAdapter) -> None:
    """Integration: fetch regions (area_leaves) for 'Moscow' from HH API."""
    req = HHSuggestionsProtocol.FetchSuggestionsRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_CITIZENSHIP, text="Москва", limit=10
    )
    candidates = await real_adapter.fetch_suggestions(req)
    assert len(candidates) > 0
    texts = [c.text or c.name for c in candidates]
    assert any("москва" in t.lower() for t in texts), f"Expected Москва in {texts}"


@pytest.mark.asyncio
@pytest.mark.real_api
async def test_fetch_suggestions_professional_role_real_api(
    real_adapter: HHSuggestionsAdapter,
) -> None:
    """Integration: fetch professional roles for 'developer' from HH API."""
    req = HHSuggestionsProtocol.FetchSuggestionsRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_PROFESSIONAL_ROLE, text="разработчик", limit=10
    )
    candidates = await real_adapter.fetch_suggestions(req)
    assert len(candidates) > 0
    texts = [c.text or c.name for c in candidates]
    assert any("разработчик" in t.lower() for t in texts), f"Expected developer-related in {texts}"


@pytest.mark.asyncio
@pytest.mark.real_api
async def test_fetch_suggestions_educational_institution_real_api(
    real_adapter: HHSuggestionsAdapter,
) -> None:
    """Integration: fetch educational institutions for 'MSU' from HH API."""
    req = HHSuggestionsProtocol.FetchSuggestionsRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_EDUCATIONAL_INSTITUTION, text="МГУ", limit=10
    )
    candidates = await real_adapter.fetch_suggestions(req)
    assert len(candidates) > 0
    texts = [c.text or c.name for c in candidates]
    assert any("мгу" in t.lower() or "московск" in t.lower() for t in texts), f"Expected MSU-related in {texts}"


@pytest.mark.asyncio
@pytest.mark.real_api
async def test_fetch_suggestions_work_ticket_real_api(real_adapter: HHSuggestionsAdapter) -> None:
    """Integration: fetch areas (work_ticket) from HH API (area_leaves, same endpoint as citizenship)."""
    req = HHSuggestionsProtocol.FetchSuggestionsRequest(
        field=hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_WORK_TICKET, text="Москва", limit=10
    )
    candidates = await real_adapter.fetch_suggestions(req)
    assert len(candidates) > 0
    texts = [c.text or c.name for c in candidates]
    assert any("москва" in t.lower() for t in texts), f"Expected Moscow-related in {texts}"
