from unittest.mock import AsyncMock

import pytest
from pydantic import HttpUrl

from nanimai_platform.domain import UserID
from nanimai_platform.protocols.external.vacancy_importer import (
    VacancyImporterError,
    VacancyImporterProtocol,
    WrongURLFormatError,
)
from nanimai_platform.services.vacancy_importer.service import (
    VacancyImporterService,
    VacancyImporterServiceError,
    VacancyImporterServiceWrongURLFormatError,
)


@pytest.mark.asyncio
async def test_import_vacancy_uses_native_adapter_when_use_hharon_false(
    vacancy_importer_service_native: VacancyImporterService,
    mock_native_adapter: VacancyImporterProtocol,
    mock_hharon_adapter: VacancyImporterProtocol,
    sample_vacancy_response: VacancyImporterProtocol.ImportVacancyResponse,
) -> None:
    """Test that native adapter is used when use_hharon is False."""
    url = HttpUrl("https://hh.ru/vacancy/123456")
    mock_native_adapter.import_vacancy = AsyncMock(return_value=sample_vacancy_response)  # type: ignore[method-assign]
    mock_hharon_adapter.import_vacancy = AsyncMock(return_value=sample_vacancy_response)  # type: ignore[method-assign]

    response = await vacancy_importer_service_native.import_vacancy(
        VacancyImporterService.ImportVacancyRequest(url=url, source="hh", user_id=UserID())
    )

    assert response.title == "Test Vacancy"
    mock_native_adapter.import_vacancy.assert_awaited_once()  # type: ignore[attr-defined]
    mock_hharon_adapter.import_vacancy.assert_not_awaited()  # type: ignore[attr-defined,method-assign]


@pytest.mark.asyncio
async def test_import_vacancy_uses_hharon_adapter_when_use_hharon_true(
    vacancy_importer_service_hharon: VacancyImporterService,
    mock_native_adapter: VacancyImporterProtocol,
    mock_hharon_adapter: VacancyImporterProtocol,
    sample_vacancy_response: VacancyImporterProtocol.ImportVacancyResponse,
) -> None:
    """Test that hharon adapter is used when use_hharon is True."""
    url = HttpUrl("https://hh.ru/vacancy/123456")
    mock_hharon_adapter.import_vacancy = AsyncMock(return_value=sample_vacancy_response)  # type: ignore[method-assign]
    mock_native_adapter.import_vacancy = AsyncMock(return_value=sample_vacancy_response)  # type: ignore[method-assign]

    response = await vacancy_importer_service_hharon.import_vacancy(
        VacancyImporterService.ImportVacancyRequest(url=url, source="hh", user_id=UserID())
    )

    assert response.title == "Test Vacancy"
    mock_hharon_adapter.import_vacancy.assert_awaited_once()  # type: ignore[attr-defined]
    mock_native_adapter.import_vacancy.assert_not_awaited()  # type: ignore[attr-defined,method-assign]


@pytest.mark.asyncio
async def test_import_vacancy_raises_wrong_url_format_error(
    vacancy_importer_service_native: VacancyImporterService,
    mock_native_adapter: VacancyImporterProtocol,
) -> None:
    """Test that WrongURLFormatError is converted to VacancyImporterServiceWrongURLFormatError."""
    url = HttpUrl("https://hh.ru/vacancy/123456")
    mock_native_adapter.import_vacancy = AsyncMock(side_effect=WrongURLFormatError("Invalid URL"))  # type: ignore[method-assign]

    with pytest.raises(VacancyImporterServiceWrongURLFormatError):
        _ = await vacancy_importer_service_native.import_vacancy(
            VacancyImporterService.ImportVacancyRequest(url=url, source="hh", user_id=UserID())
        )


@pytest.mark.asyncio
async def test_import_vacancy_raises_service_error_on_vacancy_importer_error(
    vacancy_importer_service_native: VacancyImporterService,
    mock_native_adapter: VacancyImporterProtocol,
) -> None:
    """Test that VacancyImporterError is converted to VacancyImporterServiceError."""
    url = HttpUrl("https://hh.ru/vacancy/123456")
    mock_native_adapter.import_vacancy = AsyncMock(side_effect=VacancyImporterError("Import error"))  # type: ignore[method-assign]

    with pytest.raises(VacancyImporterServiceError):
        _ = await vacancy_importer_service_native.import_vacancy(
            VacancyImporterService.ImportVacancyRequest(url=url, source="hh", user_id=UserID())
        )


def test_get_vacancy_id_uses_native_adapter_when_use_hharon_false(
    vacancy_importer_service_native: VacancyImporterService,
    mock_native_adapter: VacancyImporterProtocol,
    mock_hharon_adapter: VacancyImporterProtocol,
) -> None:
    """Test that native adapter is used for get_vacancy_id when use_hharon is False."""
    url = HttpUrl("https://hh.ru/vacancy/123456")
    mock_native_adapter.get_vacancy_id.return_value = VacancyImporterProtocol.GetVacancyIDResponse(vacancy_id="123456")  # type: ignore[attr-defined]

    response = vacancy_importer_service_native.get_vacancy_id(
        VacancyImporterService.GetVacancyIDRequest(url=url, source="hh")
    )

    assert response.vacancy_id == "123456"
    mock_native_adapter.get_vacancy_id.assert_called_once()  # type: ignore[attr-defined]
    mock_hharon_adapter.get_vacancy_id.assert_not_called()  # type: ignore[attr-defined]


def test_get_vacancy_id_uses_hharon_adapter_when_use_hharon_true(
    vacancy_importer_service_hharon: VacancyImporterService,
    mock_native_adapter: VacancyImporterProtocol,
    mock_hharon_adapter: VacancyImporterProtocol,
) -> None:
    """Test that hharon adapter is used for get_vacancy_id when use_hharon is True."""
    url = HttpUrl("https://hh.ru/vacancy/123456")
    mock_hharon_adapter.get_vacancy_id.return_value = VacancyImporterProtocol.GetVacancyIDResponse(vacancy_id="123456")  # type: ignore[attr-defined]

    response = vacancy_importer_service_hharon.get_vacancy_id(
        VacancyImporterService.GetVacancyIDRequest(url=url, source="hh")
    )

    assert response.vacancy_id == "123456"
    mock_hharon_adapter.get_vacancy_id.assert_called_once()  # type: ignore[attr-defined]
    mock_native_adapter.get_vacancy_id.assert_not_called()  # type: ignore[attr-defined]


def test_get_vacancy_id_raises_wrong_url_format_error(
    vacancy_importer_service_native: VacancyImporterService,
    mock_native_adapter: VacancyImporterProtocol,
) -> None:
    """Test that WrongURLFormatError is converted to VacancyImporterServiceWrongURLFormatError."""
    url = HttpUrl("https://hh.ru/vacancy/123456")
    mock_native_adapter.get_vacancy_id.side_effect = WrongURLFormatError("Invalid URL")  # type: ignore[attr-defined]

    with pytest.raises(VacancyImporterServiceWrongURLFormatError, match="wrong url format"):
        vacancy_importer_service_native.get_vacancy_id(VacancyImporterService.GetVacancyIDRequest(url=url, source="hh"))


def test_get_vacancy_id_raises_service_error_on_vacancy_importer_error(
    vacancy_importer_service_native: VacancyImporterService,
    mock_native_adapter: VacancyImporterProtocol,
) -> None:
    """Test that VacancyImporterError is converted to VacancyImporterServiceError."""
    url = HttpUrl("https://hh.ru/vacancy/123456")
    mock_native_adapter.get_vacancy_id.side_effect = VacancyImporterError("Import error")  # type: ignore[attr-defined]

    with pytest.raises(VacancyImporterServiceError, match="failed to get ext vacancy id"):
        vacancy_importer_service_native.get_vacancy_id(VacancyImporterService.GetVacancyIDRequest(url=url, source="hh"))
