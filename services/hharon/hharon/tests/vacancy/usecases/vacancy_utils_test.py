from unittest.mock import Mock

import pytest

from hharon.pkg import hhapi
from hharon.usecases.vacancy import vacancy_utils


@pytest.mark.parametrize(
    ("vacancy_type", "has_address", "expected_city"),
    [
        ("manager", True, "Moscow"),
        ("manager", False, None),
        ("applicant", True, "Saint Petersburg"),
        ("applicant", False, None),
    ],
)
def test_get_address_city(vacancy_type: str, has_address: bool, expected_city: str | None) -> None:
    """Test get_address_city for ForManager and ForApplicant with/without address."""
    if vacancy_type == "manager":
        vacancy = Mock(spec=hhapi.VacanciesVacancyForManager)
    else:
        vacancy = Mock(spec=hhapi.VacanciesVacancyForApplicant)

    if has_address:
        address = Mock()
        address.city = expected_city
        vacancy.address = address
    else:
        vacancy.address = None

    result = vacancy_utils.get_address_city(vacancy)

    assert result == expected_city


def test_get_expires_at_returns_value_for_manager() -> None:
    """Test get_expires_at returns expires_at for ForManager."""
    vacancy = Mock(spec=hhapi.VacanciesVacancyForManager)
    vacancy.expires_at = "2025-12-31T23:59:59+0300"

    result = vacancy_utils.get_expires_at(vacancy)

    assert result == "2025-12-31T23:59:59+0300"


def test_get_expires_at_returns_none_for_applicant() -> None:
    """Test get_expires_at returns None for ForApplicant."""
    vacancy = Mock(spec=hhapi.VacanciesVacancyForApplicant)

    result = vacancy_utils.get_expires_at(vacancy)

    assert result is None


def test_get_expires_at_returns_none_when_manager_has_no_expires_at() -> None:
    """Test get_expires_at returns None when ForManager has expires_at=None (e.g. archived vacancy)."""
    vacancy = Mock(spec=hhapi.VacanciesVacancyForManager)
    vacancy.expires_at = None

    result = vacancy_utils.get_expires_at(vacancy)

    assert result is None


def test_get_counters_returns_value_for_manager() -> None:
    """Test get_counters returns counters for ForManager."""
    vacancy = Mock(spec=hhapi.VacanciesVacancyForManager)
    mock_counters = Mock(spec=hhapi.VacancyCountersOutput)
    vacancy.counters = mock_counters

    result = vacancy_utils.get_counters(vacancy)

    assert result is mock_counters


def test_get_counters_returns_none_for_applicant() -> None:
    """Test get_counters returns None for ForApplicant."""
    vacancy = Mock(spec=hhapi.VacanciesVacancyForApplicant)

    result = vacancy_utils.get_counters(vacancy)

    assert result is None


def test_get_counters_returns_none_when_manager_has_no_counters() -> None:
    """Test get_counters returns None when ForManager has no counters (getattr fallback)."""
    vacancy = Mock(spec=hhapi.VacanciesVacancyForManager)
    vacancy.counters = None

    result = vacancy_utils.get_counters(vacancy)

    assert result is None
