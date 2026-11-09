from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import HttpUrl

from nanimai_platform.adapters.external.vacancy_importer.hharon.adapter import HHaronVacancyImporterAdapter
from nanimai_platform.domain import (
    ExperienceEnum,
    ScheduleEnum,
    VacancyStatus,
    WorkFormatEnum,
    WorkTypeEnum,
)
from nanimai_platform.protocols.external.hharon import HHaronError
from nanimai_platform.protocols.external.vacancy_importer import (
    VacancyImporterError,
    VacancyImporterProtocol,
    WrongURLFormatError,
)


@pytest.mark.asyncio
async def test_import_vacancy_calls_hharon_and_maps_response(
    hharon_vacancy_importer_adapter: HHaronVacancyImporterAdapter,
    mock_stub,
) -> None:
    """Test that import_vacancy calls hharon adapter and maps response correctly."""
    from unittest.mock import MagicMock

    url = HttpUrl("https://hh.ru/vacancy/123456")
    published_at_str = "2024-01-15T10:30:00+0300"
    published_at = datetime.strptime(published_at_str, "%Y-%m-%dT%H:%M:%S%z").astimezone(UTC)

    mock_grpc_response = MagicMock()
    mock_grpc_response.vacancy = MagicMock()
    mock_grpc_response.vacancy.name = "Python Developer"
    mock_grpc_response.vacancy.description = "<p>We need a Python developer</p>"
    mock_grpc_response.vacancy.professional_roles = ["Python Developer"]
    mock_grpc_response.vacancy.archived = False
    mock_grpc_response.vacancy.published_at = published_at_str
    mock_grpc_response.vacancy.key_skills = ["Python", "Django"]
    mock_grpc_response.vacancy.address_city = "Moscow"
    mock_grpc_response.vacancy.salary_from = 100000
    mock_grpc_response.vacancy.salary_to = 200000
    mock_grpc_response.vacancy.salary_currency = "RUB"
    mock_grpc_response.vacancy.salary_gross = None
    mock_grpc_response.vacancy.employment_form_id = "FULL"
    mock_grpc_response.vacancy.work_format_ids = ["REMOTE"]
    mock_grpc_response.vacancy.work_schedule_by_days = ["5/2"]
    mock_grpc_response.vacancy.working_hours_ids = ["HOURS_8"]
    mock_grpc_response.vacancy.experience_id = "between1And3"
    mock_grpc_response.vacancy.internship = False

    mock_stub.import_vacancy_by_url = AsyncMock(return_value=mock_grpc_response)  # type: ignore[attr-defined]

    response = await hharon_vacancy_importer_adapter.import_vacancy(
        VacancyImporterProtocol.ImportVacancyRequest(url=url)
    )

    assert response.title == "Python Developer"
    assert "We need a Python developer" in response.description
    assert response.specialization == "Python Developer"
    assert response.status == VacancyStatus.OPEN
    assert response.city == "Moscow"
    assert response.salary is not None
    assert response.salary.min == 100000
    assert response.salary.max == 200000
    assert response.work_type == WorkTypeEnum.FULL_TIME
    assert WorkFormatEnum.REMOTE in response.work_format
    assert ScheduleEnum.SCHEDULE_5_2 in response.schedule
    assert 8 in response.daily_rate
    assert response.experience == ExperienceEnum.EXP_1_3
    assert len(response.skills) == 2
    assert any(skill.title == "Python" for skill in response.skills)
    assert response.is_internship is False
    assert response.published_at == published_at

    mock_stub.import_vacancy_by_url.assert_awaited_once()  # type: ignore[attr-defined]


def _create_mock_grpc_vacancy_response(
    name: str = "Test Vacancy",
    description: str = "Test description",
    professional_roles: list[str] | None = None,
    archived: bool = False,
    published_at: str = "2024-01-15T10:30:00+0300",
    key_skills: list[str] | None = None,
    address_city: str | None = "Moscow",
    salary_from: int | None = None,
    salary_to: int | None = None,
    salary_currency: str | None = None,
    salary_gross: bool | None = None,
    employment_form_id: str | None = None,
    work_format_ids: list[str] | None = None,
    work_schedule_by_days: list[str] | None = None,
    working_hours_ids: list[str] | None = None,
    experience_id: str | None = None,
    internship: bool = False,
) -> MagicMock:
    """Helper to create mock gRPC vacancy response."""
    mock_grpc_response = MagicMock()
    mock_grpc_response.vacancy = MagicMock()
    mock_grpc_response.vacancy.name = name
    mock_grpc_response.vacancy.description = description
    mock_grpc_response.vacancy.professional_roles = professional_roles or []
    mock_grpc_response.vacancy.archived = archived
    mock_grpc_response.vacancy.published_at = published_at
    mock_grpc_response.vacancy.key_skills = key_skills or []
    mock_grpc_response.vacancy.address_city = address_city
    mock_grpc_response.vacancy.salary_from = salary_from
    mock_grpc_response.vacancy.salary_to = salary_to
    mock_grpc_response.vacancy.salary_currency = salary_currency
    mock_grpc_response.vacancy.salary_gross = salary_gross
    mock_grpc_response.vacancy.employment_form_id = employment_form_id
    mock_grpc_response.vacancy.work_format_ids = work_format_ids or []
    mock_grpc_response.vacancy.work_schedule_by_days = work_schedule_by_days or []
    mock_grpc_response.vacancy.working_hours_ids = working_hours_ids or []
    mock_grpc_response.vacancy.experience_id = experience_id
    mock_grpc_response.vacancy.internship = internship
    return mock_grpc_response


@pytest.mark.asyncio
async def test_import_vacancy_by_id_creates_url_and_calls_hharon(
    hharon_vacancy_importer_adapter: HHaronVacancyImporterAdapter,
    mock_stub,
) -> None:
    """Test that import_vacancy_by_id creates URL from ID and calls hharon."""
    vacancy_id = "123456"
    published_at_str = "2024-01-15T10:30:00+0300"

    mock_grpc_response = _create_mock_grpc_vacancy_response(
        name="Test Vacancy",
        description="Test description",
        professional_roles=["Developer"],
        published_at=published_at_str,
        employment_form_id="FULL",
        experience_id="noExperience",
    )

    mock_stub.import_vacancy_by_url = AsyncMock(return_value=mock_grpc_response)  # type: ignore[attr-defined]

    response = await hharon_vacancy_importer_adapter.import_vacancy(
        VacancyImporterProtocol.ImportVacancyRequest(url=HttpUrl(f"https://hh.ru/vacancy/{vacancy_id}"))
    )

    assert response.title == "Test Vacancy"
    mock_stub.import_vacancy_by_url.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_import_vacancy_handles_archived_vacancy(
    hharon_vacancy_importer_adapter: HHaronVacancyImporterAdapter,
    mock_stub,
) -> None:
    """Test that archived vacancies are mapped correctly."""
    url = HttpUrl("https://hh.ru/vacancy/123456")
    published_at_str = "2024-01-15T10:30:00+0300"

    mock_grpc_response = _create_mock_grpc_vacancy_response(
        name="Archived Vacancy",
        description="Description",
        archived=True,
        published_at=published_at_str,
        employment_form_id="FULL",
        experience_id="noExperience",
    )

    mock_stub.import_vacancy_by_url = AsyncMock(return_value=mock_grpc_response)  # type: ignore[attr-defined]

    response = await hharon_vacancy_importer_adapter.import_vacancy(
        VacancyImporterProtocol.ImportVacancyRequest(url=url)
    )

    assert response.status == VacancyStatus.ARCHIVED


@pytest.mark.asyncio
async def test_import_vacancy_handles_salary_mapping(
    hharon_vacancy_importer_adapter: HHaronVacancyImporterAdapter,
    mock_stub,
) -> None:
    """Test that salary is mapped correctly from hharon response."""
    url = HttpUrl("https://hh.ru/vacancy/123456")
    published_at_str = "2024-01-15T10:30:00+0300"

    mock_grpc_response = _create_mock_grpc_vacancy_response(
        name="Vacancy with Salary",
        description="Description",
        published_at=published_at_str,
        salary_from=150000,
        salary_to=250000,
        salary_currency="USD",
        employment_form_id="FULL",
        experience_id="noExperience",
    )

    mock_stub.import_vacancy_by_url = AsyncMock(return_value=mock_grpc_response)  # type: ignore[attr-defined]

    response = await hharon_vacancy_importer_adapter.import_vacancy(
        VacancyImporterProtocol.ImportVacancyRequest(url=url)
    )

    assert response.salary is not None
    assert response.salary.min == 150000
    assert response.salary.max == 250000
    assert response.salary.currency == "USD"


@pytest.mark.asyncio
async def test_import_vacancy_handles_no_salary(
    hharon_vacancy_importer_adapter: HHaronVacancyImporterAdapter,
    mock_stub,
) -> None:
    """Test that vacancy without salary is handled correctly."""
    url = HttpUrl("https://hh.ru/vacancy/123456")
    published_at_str = "2024-01-15T10:30:00+0300"

    mock_grpc_response = _create_mock_grpc_vacancy_response(
        name="Vacancy without Salary",
        description="Description",
        published_at=published_at_str,
        employment_form_id="FULL",
        experience_id="noExperience",
    )

    mock_stub.import_vacancy_by_url = AsyncMock(return_value=mock_grpc_response)  # type: ignore[attr-defined]

    response = await hharon_vacancy_importer_adapter.import_vacancy(
        VacancyImporterProtocol.ImportVacancyRequest(url=url)
    )

    assert response.salary is None


@pytest.mark.asyncio
async def test_import_vacancy_handles_work_format_mapping(
    hharon_vacancy_importer_adapter: HHaronVacancyImporterAdapter,
    mock_stub,
) -> None:
    """Test that work format IDs are mapped correctly."""
    url = HttpUrl("https://hh.ru/vacancy/123456")
    published_at_str = "2024-01-15T10:30:00+0300"

    mock_grpc_response = _create_mock_grpc_vacancy_response(
        name="Vacancy",
        description="Description",
        published_at=published_at_str,
        employment_form_id="FULL",
        work_format_ids=["REMOTE", "HYBRID", "ON_SITE"],
        experience_id="noExperience",
    )

    mock_stub.import_vacancy_by_url = AsyncMock(return_value=mock_grpc_response)  # type: ignore[attr-defined]

    response = await hharon_vacancy_importer_adapter.import_vacancy(
        VacancyImporterProtocol.ImportVacancyRequest(url=url)
    )

    assert WorkFormatEnum.REMOTE in response.work_format
    assert WorkFormatEnum.HYBRID in response.work_format
    assert WorkFormatEnum.OFFICE in response.work_format
    assert len(response.work_format) == 3


@pytest.mark.asyncio
async def test_import_vacancy_handles_schedule_mapping(
    hharon_vacancy_importer_adapter: HHaronVacancyImporterAdapter,
    mock_stub,
) -> None:
    """Test that work schedule is mapped correctly."""
    url = HttpUrl("https://hh.ru/vacancy/123456")
    published_at_str = "2024-01-15T10:30:00+0300"

    mock_grpc_response = _create_mock_grpc_vacancy_response(
        name="Vacancy",
        description="Description",
        published_at=published_at_str,
        employment_form_id="FULL",
        work_schedule_by_days=["5/2", "2/2"],
        experience_id="noExperience",
    )

    mock_stub.import_vacancy_by_url = AsyncMock(return_value=mock_grpc_response)  # type: ignore[attr-defined]

    response = await hharon_vacancy_importer_adapter.import_vacancy(
        VacancyImporterProtocol.ImportVacancyRequest(url=url)
    )

    assert ScheduleEnum.SCHEDULE_5_2 in response.schedule
    assert ScheduleEnum.SCHEDULE_2_2 in response.schedule
    assert len(response.schedule) == 2


@pytest.mark.asyncio
async def test_import_vacancy_handles_daily_rate_mapping(
    hharon_vacancy_importer_adapter: HHaronVacancyImporterAdapter,
    mock_stub,
) -> None:
    """Test that working hours IDs are mapped to daily rate correctly."""
    url = HttpUrl("https://hh.ru/vacancy/123456")
    published_at_str = "2024-01-15T10:30:00+0300"

    mock_grpc_response = _create_mock_grpc_vacancy_response(
        name="Vacancy",
        description="Description",
        published_at=published_at_str,
        employment_form_id="FULL",
        working_hours_ids=["HOURS_8", "HOURS_6"],
        experience_id="noExperience",
    )

    mock_stub.import_vacancy_by_url = AsyncMock(return_value=mock_grpc_response)  # type: ignore[attr-defined]

    response = await hharon_vacancy_importer_adapter.import_vacancy(
        VacancyImporterProtocol.ImportVacancyRequest(url=url)
    )

    assert 8 in response.daily_rate
    assert 6 in response.daily_rate
    assert len(response.daily_rate) == 2


@pytest.mark.asyncio
async def test_import_vacancy_handles_experience_mapping(
    hharon_vacancy_importer_adapter: HHaronVacancyImporterAdapter,
    mock_stub,
) -> None:
    """Test that experience ID is mapped correctly."""
    url = HttpUrl("https://hh.ru/vacancy/123456")
    published_at_str = "2024-01-15T10:30:00+0300"

    test_cases = [
        ("noExperience", ExperienceEnum.EXP_0),
        ("between1And3", ExperienceEnum.EXP_1_3),
        ("between3And6", ExperienceEnum.EXP_3_6),
        ("moreThan6", ExperienceEnum.EXP_6_PLUS),
    ]

    for experience_id, expected_enum in test_cases:
        mock_grpc_response = _create_mock_grpc_vacancy_response(
            name="Vacancy",
            description="Description",
            published_at=published_at_str,
            employment_form_id="FULL",
            experience_id=experience_id,
        )

        mock_stub.import_vacancy_by_url = AsyncMock(return_value=mock_grpc_response)  # type: ignore[attr-defined]

        response = await hharon_vacancy_importer_adapter.import_vacancy(
            VacancyImporterProtocol.ImportVacancyRequest(url=url)
        )

        assert response.experience == expected_enum


@pytest.mark.asyncio
async def test_import_vacancy_handles_skills_mapping(
    hharon_vacancy_importer_adapter: HHaronVacancyImporterAdapter,
    mock_stub,
) -> None:
    """Test that key skills are mapped correctly."""
    url = HttpUrl("https://hh.ru/vacancy/123456")
    published_at_str = "2024-01-15T10:30:00+0300"

    mock_grpc_response = _create_mock_grpc_vacancy_response(
        name="Vacancy",
        description="Description",
        published_at=published_at_str,
        key_skills=["Python", "Django", "PostgreSQL"],
        employment_form_id="FULL",
        experience_id="noExperience",
    )

    mock_stub.import_vacancy_by_url = AsyncMock(return_value=mock_grpc_response)  # type: ignore[attr-defined]

    response = await hharon_vacancy_importer_adapter.import_vacancy(
        VacancyImporterProtocol.ImportVacancyRequest(url=url)
    )

    assert len(response.skills) == 3
    skill_titles = [skill.title for skill in response.skills]
    assert "Python" in skill_titles
    assert "Django" in skill_titles
    assert "PostgreSQL" in skill_titles


@pytest.mark.asyncio
async def test_import_vacancy_handles_internship(
    hharon_vacancy_importer_adapter: HHaronVacancyImporterAdapter,
    mock_stub,
) -> None:
    """Test that internship flag is mapped correctly."""
    url = HttpUrl("https://hh.ru/vacancy/123456")
    published_at_str = "2024-01-15T10:30:00+0300"

    mock_grpc_response = _create_mock_grpc_vacancy_response(
        name="Internship Vacancy",
        description="Description",
        published_at=published_at_str,
        employment_form_id="FULL",
        experience_id="noExperience",
        internship=True,
    )

    mock_stub.import_vacancy_by_url = AsyncMock(return_value=mock_grpc_response)  # type: ignore[attr-defined]

    response = await hharon_vacancy_importer_adapter.import_vacancy(
        VacancyImporterProtocol.ImportVacancyRequest(url=url)
    )

    assert response.is_internship is True


@pytest.mark.asyncio
async def test_import_vacancy_raises_error_on_hharon_error(
    hharon_vacancy_importer_adapter: HHaronVacancyImporterAdapter,
    mock_stub,
) -> None:
    """Test that VacancyImporterError is raised when hharon adapter raises error."""
    url = HttpUrl("https://hh.ru/vacancy/123456")

    mock_stub.import_vacancy_by_url = AsyncMock(side_effect=HHaronError("HHaron error"))  # type: ignore[attr-defined]

    with pytest.raises(VacancyImporterError, match="Unexpected error"):
        await hharon_vacancy_importer_adapter.import_vacancy(VacancyImporterProtocol.ImportVacancyRequest(url=url))


def test_get_vacancy_id_extracts_id_from_url(hharon_vacancy_importer_adapter: HHaronVacancyImporterAdapter) -> None:
    """Test that get_vacancy_id extracts vacancy ID from URL correctly."""
    url = HttpUrl("https://hh.ru/vacancy/123456")

    response = hharon_vacancy_importer_adapter.get_vacancy_id(VacancyImporterProtocol.GetVacancyIDRequest(url=url))

    assert response.vacancy_id == "123456"


def test_get_vacancy_id_works_with_vacancies_path(
    hharon_vacancy_importer_adapter: HHaronVacancyImporterAdapter,
) -> None:
    """Test that get_vacancy_id works with /vacancies/ path."""
    url = HttpUrl("https://hh.ru/vacancies/789012")

    response = hharon_vacancy_importer_adapter.get_vacancy_id(VacancyImporterProtocol.GetVacancyIDRequest(url=url))

    assert response.vacancy_id == "789012"


def test_get_vacancy_id_raises_error_on_invalid_url(
    hharon_vacancy_importer_adapter: HHaronVacancyImporterAdapter,
) -> None:
    """Test that get_vacancy_id raises WrongURLFormatError for invalid URLs."""
    # Test invalid domain
    with pytest.raises(WrongURLFormatError):
        hharon_vacancy_importer_adapter.get_vacancy_id(
            VacancyImporterProtocol.GetVacancyIDRequest(url=HttpUrl("https://example.com/vacancy/123"))
        )

    # Test missing vacancy ID in path (path is just "/vacancy" without ID)
    with pytest.raises(WrongURLFormatError, match="Vacancy ID is missing"):
        hharon_vacancy_importer_adapter.get_vacancy_id(
            VacancyImporterProtocol.GetVacancyIDRequest(url=HttpUrl("https://hh.ru/vacancy"))
        )


def test_get_vacancy_id_works_with_different_domains(
    hharon_vacancy_importer_adapter: HHaronVacancyImporterAdapter,
) -> None:
    """Test that get_vacancy_id works with different HH domains."""
    test_cases = [
        ("https://hh.ru/vacancy/123", "123"),
        ("https://rabota.by/vacancy/456", "456"),
        ("https://hh.kz/vacancy/789", "789"),
    ]

    for url_str, expected_id in test_cases:
        url = HttpUrl(url_str)
        response = hharon_vacancy_importer_adapter.get_vacancy_id(VacancyImporterProtocol.GetVacancyIDRequest(url=url))
        assert response.vacancy_id == expected_id
