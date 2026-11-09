from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest

from hharon.adapters.vacancy import HHGetVacancyAdapter
from hharon.infra.headhunter import HHHTTPError, HeadHunterClient
from hharon.pkg import hhapi
from hharon.protocols import vacancy as vacancy_protocol


@pytest.fixture
def mock_hh_client() -> Mock:
    """Create a mock HeadHunterClient."""
    return Mock(spec=HeadHunterClient)


@pytest.fixture
def adapter(mock_hh_client: Mock) -> HHGetVacancyAdapter:
    """Create HHGetVacancyAdapter for testing."""
    return HHGetVacancyAdapter(client=cast("HeadHunterClient", mock_hh_client))


def _make_mock_vacancy_response() -> Mock:
    mock_manager = Mock(spec=hhapi.VacanciesVacancyForManager)
    mock_vacancy = Mock(spec=hhapi.VacanciesVacancy)
    mock_vacancy.root = mock_manager
    return mock_vacancy


@pytest.mark.asyncio
async def test_get_vacancy_by_id_returns_manager_vacancy_with_token(
    adapter: HHGetVacancyAdapter, mock_hh_client: Mock
) -> None:
    """Test that get_vacancy_by_id returns vacancy when request succeeds with token."""
    vacancy_id = "123456"
    request = vacancy_protocol.GetVacancyByIDProtocol.GetVacancyByIDRequest(
        access_token="test_token",
        vacancy_id=vacancy_id,
    )

    mock_vacancy = _make_mock_vacancy_response()
    mock_hh_client.get = AsyncMock(return_value=mock_vacancy)

    result = await adapter.get_vacancy_by_id(request)

    assert result is mock_vacancy.root
    mock_hh_client.get.assert_awaited_once_with(
        f"/vacancies/{vacancy_id}",
        response_model=hhapi.VacanciesVacancy,
        headers={"Authorization": "Bearer test_token"},
    )


@pytest.mark.asyncio
async def test_get_vacancy_by_id_returns_applicant_vacancy_without_token(
    adapter: HHGetVacancyAdapter, mock_hh_client: Mock
) -> None:
    """Test that get_vacancy_by_id returns vacancy when no token (applicant view)."""
    vacancy_id = "123456"
    request = vacancy_protocol.GetVacancyByIDProtocol.GetVacancyByIDRequest(
        access_token=None,
        vacancy_id=vacancy_id,
    )

    mock_applicant_vacancy = Mock(spec=hhapi.VacanciesVacancyForApplicant)
    mock_vacancy = Mock(spec=hhapi.VacanciesVacancy)
    mock_vacancy.root = mock_applicant_vacancy
    mock_hh_client.get = AsyncMock(return_value=mock_vacancy)

    result = await adapter.get_vacancy_by_id(request)

    assert result is mock_applicant_vacancy
    mock_hh_client.get.assert_awaited_once_with(
        f"/vacancies/{vacancy_id}",
        response_model=hhapi.VacanciesVacancy,
        headers={},
    )


@pytest.mark.asyncio
async def test_get_vacancy_by_id_raises_access_denied_on_403_with_token(
    adapter: HHGetVacancyAdapter, mock_hh_client: Mock
) -> None:
    """Test that get_vacancy_by_id raises AccessDenied when 403 with token."""
    vacancy_id = "123456"
    request = vacancy_protocol.GetVacancyByIDProtocol.GetVacancyByIDRequest(
        access_token="test_token",
        vacancy_id=vacancy_id,
    )

    error_403 = HHHTTPError(message="Forbidden", status_code=403, response_text="Forbidden")
    mock_hh_client.get = AsyncMock(side_effect=error_403)

    with pytest.raises(vacancy_protocol.GetVacancyByIDAccessDeniedError):
        await adapter.get_vacancy_by_id(request)

    mock_hh_client.get.assert_awaited_once_with(
        f"/vacancies/{vacancy_id}",
        response_model=hhapi.VacanciesVacancy,
        headers={"Authorization": "Bearer test_token"},
    )


@pytest.mark.asyncio
async def test_get_vacancy_by_id_raises_access_denied_on_403_without_token(
    adapter: HHGetVacancyAdapter, mock_hh_client: Mock
) -> None:
    """Test that get_vacancy_by_id raises AccessDenied when 403 and no token."""
    vacancy_id = "123456"
    request = vacancy_protocol.GetVacancyByIDProtocol.GetVacancyByIDRequest(
        access_token=None,
        vacancy_id=vacancy_id,
    )

    error_403 = HHHTTPError(message="Forbidden", status_code=403, response_text="Forbidden")
    mock_hh_client.get = AsyncMock(side_effect=error_403)

    with pytest.raises(vacancy_protocol.GetVacancyByIDAccessDeniedError):
        await adapter.get_vacancy_by_id(request)

    mock_hh_client.get.assert_awaited_once_with(
        f"/vacancies/{vacancy_id}",
        response_model=hhapi.VacanciesVacancy,
        headers={},
    )


@pytest.mark.asyncio
async def test_get_vacancy_by_id_raises_on_500_with_token(adapter: HHGetVacancyAdapter, mock_hh_client: Mock) -> None:
    """Test that get_vacancy_by_id raises on 500 (no fallback for server errors)."""
    vacancy_id = "123456"
    request = vacancy_protocol.GetVacancyByIDProtocol.GetVacancyByIDRequest(
        access_token="test_token",
        vacancy_id=vacancy_id,
    )

    error_500 = HHHTTPError(message="Internal Server Error", status_code=500, response_text="Internal Server Error")
    mock_hh_client.get = AsyncMock(side_effect=error_500)

    with pytest.raises(vacancy_protocol.GetVacancyByIDError):
        await adapter.get_vacancy_by_id(request)

    mock_hh_client.get.assert_awaited_once()
