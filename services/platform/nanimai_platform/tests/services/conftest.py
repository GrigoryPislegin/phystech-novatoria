from datetime import UTC, datetime
from unittest.mock import create_autospec

import pytest

from nanimai_platform.domain import ExperienceEnum, Skill, VacancyStatus, WorkTypeEnum
from nanimai_platform.infra.config import HHVacancyImporterConfig
from nanimai_platform.protocols.external.vacancy_importer import VacancyImporterProtocol
from nanimai_platform.services.vacancy_importer.service import VacancyImporterService


@pytest.fixture
def mock_native_adapter() -> VacancyImporterProtocol:
    return create_autospec(VacancyImporterProtocol, instance=True, spec_set=True)


@pytest.fixture
def mock_hharon_adapter() -> VacancyImporterProtocol:
    return create_autospec(VacancyImporterProtocol, instance=True, spec_set=True)


@pytest.fixture
def vacancy_importer_service_native(
    mock_native_adapter: VacancyImporterProtocol, mock_hharon_adapter: VacancyImporterProtocol
) -> VacancyImporterService:
    config = HHVacancyImporterConfig(use_hharon=False)
    return VacancyImporterService(
        native_hh_vacancy_importer_adapter=mock_native_adapter,
        hharon_vacancy_importer_adapter=mock_hharon_adapter,
        hh_vacancy_importer_cfg=config,
    )


@pytest.fixture
def vacancy_importer_service_hharon(
    mock_native_adapter: VacancyImporterProtocol, mock_hharon_adapter: VacancyImporterProtocol
) -> VacancyImporterService:
    config = HHVacancyImporterConfig(use_hharon=True)
    return VacancyImporterService(
        native_hh_vacancy_importer_adapter=mock_native_adapter,
        hharon_vacancy_importer_adapter=mock_hharon_adapter,
        hh_vacancy_importer_cfg=config,
    )


@pytest.fixture
def sample_vacancy_response() -> VacancyImporterProtocol.ImportVacancyResponse:
    return VacancyImporterProtocol.ImportVacancyResponse(
        title="Test Vacancy",
        description="Test description",
        specialization="Developer",
        status=VacancyStatus.OPEN,
        city="Moscow",
        country=None,
        hire_amount=None,
        salary=None,
        work_type=WorkTypeEnum.FULL_TIME,
        work_format=[],
        is_internship=False,
        is_temphire=False,
        schedule=[],
        daily_rate=[],
        experience=ExperienceEnum.EXP_0,
        skills=[Skill(title="Python")],
        published_at=datetime.now(UTC),
    )
