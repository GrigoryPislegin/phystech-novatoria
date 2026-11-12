from hharon.pkg.hhapi.models import (
    VacanciesVacancyForApplicant,
    VacanciesVacancyForManager,
    VacancyCountersOutput,
)

VacancyUnion = VacanciesVacancyForApplicant | VacanciesVacancyForManager


def get_address_city(vacancy: VacancyUnion) -> str | None:
    """Город из address. Безопасно для обоих типов."""
    address = vacancy.address
    return address.city if address else None


def get_expires_at(vacancy: VacancyUnion) -> str | None:
    """expires_at только у ForManager."""
    if isinstance(vacancy, VacanciesVacancyForManager):
        return vacancy.expires_at
    return None


def get_counters(vacancy: VacancyUnion) -> VacancyCountersOutput | None:
    """counters только у ForManager."""
    if isinstance(vacancy, VacanciesVacancyForManager):
        return vacancy.counters
    return None
