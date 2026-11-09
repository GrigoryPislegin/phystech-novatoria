from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest

from hharon.adapters.response_collection.hh_api import HeadHunterResponseCollectionAdapter
from hharon.infra.headhunter import HHHTTPError, HeadHunterClient
from hharon.pkg import hhapi
from hharon.pkg.hhapi.models import Item2, NegotiationsCollectionNegotiationsResponse, ResumeResumeForEmployer
from hharon.protocols.response_collection import (
    HeadHunterAccessDeniedError,
    HeadHunterRateLimitError,
    HeadHunterResponseCollectionError,
)
from hharon.protocols.response_collection.hh_protocol import (
    ResponseCollectionPreviewHHApiAccessDeniedError,
    ResponseCollectionPreviewHHApiNotFoundError,
)


@pytest.fixture
def mock_hh_client() -> Mock:
    """Create a mock HeadHunterClient."""
    return Mock(spec=HeadHunterClient)


@pytest.fixture
def adapter(mock_hh_client: Mock) -> HeadHunterResponseCollectionAdapter:
    """Create HeadHunterResponseCollectionAdapter for testing."""
    return HeadHunterResponseCollectionAdapter(client=cast("HeadHunterClient", mock_hh_client))


@pytest.mark.asyncio
async def test_get_responses_from_collection_yields_items(
    adapter: HeadHunterResponseCollectionAdapter, mock_hh_client: Mock
) -> None:
    """Test that get_responses_from_collection yields response items."""
    collection_id = "collection_123"
    vacancy_id = "vacancy_456"

    # Mock response with items
    item1 = Mock(spec=Item2)
    item2 = Mock(spec=Item2)
    response = Mock(spec=NegotiationsCollectionNegotiationsResponse)
    response.items = [item1, item2]
    response.pages = 1

    mock_hh_client.get = AsyncMock(return_value=response)

    items = [
        item
        async for item in adapter.get_responses_from_collection(
            collection_id=collection_id, vacancy_id=vacancy_id, access_token="test_token"
        )
    ]

    assert len(items) == 2
    assert items[0] == item1
    assert items[1] == item2

    mock_hh_client.get.assert_awaited_once()  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_get_responses_from_collection_handles_pagination(
    adapter: HeadHunterResponseCollectionAdapter, mock_hh_client: Mock
) -> None:
    """Test that get_responses_from_collection handles pagination correctly."""
    collection_id = "collection_123"
    vacancy_id = "vacancy_456"

    # First page (page 0)
    item1 = Mock(spec=Item2)
    response1 = Mock(spec=NegotiationsCollectionNegotiationsResponse)
    response1.items = [item1]
    response1.pages = 2

    # Second page (page 1) - last page, stops after this
    item2 = Mock(spec=Item2)
    response2 = Mock(spec=NegotiationsCollectionNegotiationsResponse)
    response2.items = [item2]
    response2.pages = 2

    mock_hh_client.get = AsyncMock(side_effect=[response1, response2])

    items = [
        item
        async for item in adapter.get_responses_from_collection(
            collection_id=collection_id, vacancy_id=vacancy_id, access_token="test_token"
        )
    ]

    assert len(items) == 2
    assert items[0] == item1
    assert items[1] == item2
    # Should call 2 times (page 0 and page 1, then stop because page >= pages - 1)
    assert mock_hh_client.get.await_count == 2  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_get_responses_from_collection_raises_rate_limit_error(
    adapter: HeadHunterResponseCollectionAdapter, mock_hh_client: Mock
) -> None:
    """Test that get_responses_from_collection raises HeadHunterRateLimitError on 429."""
    collection_id = "collection_123"
    vacancy_id = "vacancy_456"

    error = HHHTTPError(message="Rate limit", status_code=429, response_text='{"retry_after": 60}')
    mock_hh_client.get = AsyncMock(side_effect=error)

    with pytest.raises(HeadHunterRateLimitError) as exc_info:
        async for _ in adapter.get_responses_from_collection(
            collection_id=collection_id, vacancy_id=vacancy_id, access_token="test_token"
        ):
            pass

    assert exc_info.value.retry_after == 60


@pytest.mark.asyncio
async def test_get_responses_from_collection_raises_access_denied_error_on_403(
    adapter: HeadHunterResponseCollectionAdapter, mock_hh_client: Mock
) -> None:
    """Test that get_responses_from_collection raises HeadHunterAccessDeniedError on 403."""
    collection_id = "collection_123"
    vacancy_id = "vacancy_456"

    error = HHHTTPError(message="Forbidden", status_code=403, response_text="Forbidden")
    mock_hh_client.get = AsyncMock(side_effect=error)

    with pytest.raises(HeadHunterAccessDeniedError):
        async for _ in adapter.get_responses_from_collection(
            collection_id=collection_id, vacancy_id=vacancy_id, access_token="test_token"
        ):
            pass


@pytest.mark.asyncio
async def test_get_responses_from_collection_raises_access_denied_error_on_404(
    adapter: HeadHunterResponseCollectionAdapter, mock_hh_client: Mock
) -> None:
    """Test that get_responses_from_collection raises HeadHunterAccessDeniedError on 404."""
    collection_id = "collection_123"
    vacancy_id = "vacancy_456"

    error = HHHTTPError(message="Not Found", status_code=404, response_text="Not Found")
    mock_hh_client.get = AsyncMock(side_effect=error)

    with pytest.raises(HeadHunterAccessDeniedError):
        async for _ in adapter.get_responses_from_collection(
            collection_id=collection_id, vacancy_id=vacancy_id, access_token="test_token"
        ):
            pass


@pytest.mark.asyncio
async def test_get_resume_returns_resume(adapter: HeadHunterResponseCollectionAdapter, mock_hh_client: Mock) -> None:
    """Test that get_resume returns resume data."""
    resume_id = "resume_789"
    resume = Mock(spec=ResumeResumeForEmployer)

    mock_hh_client.get = AsyncMock(return_value=resume)

    result = await adapter.get_resume(resume_id=resume_id, access_token="test_token")

    assert result == resume

    mock_hh_client.get.assert_awaited_once()  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_get_resume_raises_rate_limit_error(
    adapter: HeadHunterResponseCollectionAdapter, mock_hh_client: Mock
) -> None:
    """Test that get_resume raises HeadHunterRateLimitError on 429."""
    resume_id = "resume_789"

    error = HHHTTPError(message="Rate limit", status_code=429, response_text='{"retry_after": 120}')
    mock_hh_client.get = AsyncMock(side_effect=error)

    with pytest.raises(HeadHunterRateLimitError) as exc_info:
        await adapter.get_resume(resume_id=resume_id, access_token="test_token")

    assert exc_info.value.retry_after == 120


@pytest.mark.asyncio
async def test_get_resume_raises_access_denied_error_on_403(
    adapter: HeadHunterResponseCollectionAdapter, mock_hh_client: Mock
) -> None:
    """Test that get_resume raises HeadHunterAccessDeniedError on 403."""
    resume_id = "resume_789"

    error = HHHTTPError(message="Forbidden", status_code=403, response_text="Forbidden")
    mock_hh_client.get = AsyncMock(side_effect=error)

    with pytest.raises(HeadHunterAccessDeniedError):
        await adapter.get_resume(resume_id=resume_id, access_token="test_token")


@pytest.mark.asyncio
async def test_get_resume_raises_access_denied_error_on_404(
    adapter: HeadHunterResponseCollectionAdapter, mock_hh_client: Mock
) -> None:
    """Test that get_resume raises HeadHunterAccessDeniedError on 404."""
    resume_id = "resume_789"

    error = HHHTTPError(message="Not Found", status_code=404, response_text="Not Found")
    mock_hh_client.get = AsyncMock(side_effect=error)

    with pytest.raises(HeadHunterAccessDeniedError):
        await adapter.get_resume(resume_id=resume_id, access_token="test_token")


@pytest.mark.asyncio
async def test_get_resume_raises_error_on_other_http_error(
    adapter: HeadHunterResponseCollectionAdapter, mock_hh_client: Mock
) -> None:
    """Test that get_resume raises HeadHunterResponseCollectionError on other HTTP errors."""
    resume_id = "resume_789"

    error = HHHTTPError(message="Internal Server Error", status_code=500, response_text="Internal Server Error")
    mock_hh_client.get = AsyncMock(side_effect=error)

    with pytest.raises(HeadHunterResponseCollectionError):
        await adapter.get_resume(resume_id=resume_id, access_token="test_token")


@pytest.mark.asyncio
async def test_get_vacancies_vacancy_id_returns_manager_vacancy(
    adapter: HeadHunterResponseCollectionAdapter, mock_hh_client: Mock
) -> None:
    """Test that get_vacancies_vacancy_id returns manager vacancy on success."""
    hh_vacancy_id = "123456"
    mock_manager_vacancy = Mock(spec=hhapi.VacanciesVacancyForManager)
    mock_vacancy = Mock(spec=hhapi.VacanciesVacancy)
    mock_vacancy.root = mock_manager_vacancy
    mock_hh_client.get = AsyncMock(return_value=mock_vacancy)

    result = await adapter.get_vacancies_vacancy_id(access_token="test_token", hh_vacancy_id=hh_vacancy_id)

    assert result is mock_manager_vacancy
    mock_hh_client.get.assert_awaited_once_with(
        f"/vacancies/{hh_vacancy_id}",
        response_model=hhapi.VacanciesVacancy,
        headers={"Authorization": "Bearer test_token"},
    )


@pytest.mark.asyncio
async def test_get_vacancies_vacancy_id_raises_access_denied_on_403(
    adapter: HeadHunterResponseCollectionAdapter, mock_hh_client: Mock
) -> None:
    """Test that get_vacancies_vacancy_id raises AccessDeniedError on 403."""
    hh_vacancy_id = "123456"
    error_403 = HHHTTPError(message="Forbidden", status_code=403, response_text="Forbidden")
    mock_hh_client.get = AsyncMock(side_effect=error_403)

    with pytest.raises(ResponseCollectionPreviewHHApiAccessDeniedError):
        await adapter.get_vacancies_vacancy_id(access_token="test_token", hh_vacancy_id=hh_vacancy_id)

    mock_hh_client.get.assert_awaited_once_with(
        f"/vacancies/{hh_vacancy_id}",
        response_model=hhapi.VacanciesVacancy,
        headers={"Authorization": "Bearer test_token"},
    )


@pytest.mark.asyncio
async def test_get_vacancies_vacancy_id_raises_not_found_on_404(
    adapter: HeadHunterResponseCollectionAdapter, mock_hh_client: Mock
) -> None:
    """Test that get_vacancies_vacancy_id raises NotFoundError on 404."""
    hh_vacancy_id = "123456"
    error_404 = HHHTTPError(message="Not Found", status_code=404, response_text="Not Found")
    mock_hh_client.get = AsyncMock(side_effect=error_404)

    with pytest.raises(ResponseCollectionPreviewHHApiNotFoundError):
        await adapter.get_vacancies_vacancy_id(access_token="test_token", hh_vacancy_id=hh_vacancy_id)

    mock_hh_client.get.assert_awaited_once()
