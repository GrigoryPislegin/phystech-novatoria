from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, create_autospec, patch

import pytest

from nanimai_platform import domain
from nanimai_platform.domain.skill import Skill
from nanimai_platform.domain.vacancy import vacancy as vacancy_domain
from nanimai_platform.protocols.external.candidate_polling import CandidatePollingProtocol
from nanimai_platform.protocols.external.vacancy_importer import VacancyImporterProtocol
from nanimai_platform.services.cache.cache import Cache
from nanimai_platform.services.candidate.service import CandidateService
from nanimai_platform.services.candidate_polling_v2.hh import HHCandidatePollingV2Service
from nanimai_platform.services.llm.service import LLMService
from nanimai_platform.services.oauth2.service import OAuth2Service
from nanimai_platform.services.user_profile.service import UserService
from nanimai_platform.services.vacancy.service import VacancyService


def _make_vacancy(
    *,
    status: vacancy_domain.VacancyStatus,
    hh_state: vacancy_domain.PublicationStatusEnum,
    hh_publication_id: str | None,
) -> domain.Vacancy:
    now = datetime.now(UTC)
    return domain.Vacancy(
        id=domain.VacancyID("507f1f77bcf86cd799439011"),
        user_id=domain.UserID("507f1f77bcf86cd799439012"),
        project_id=domain.ProjectID("507f1f77bcf86cd799439013"),
        title="t",
        description="d",
        specialization="s",
        thumbnail_url="http://example.com/x.png",
        status=status,
        city=None,
        country=None,
        hire_amount=None,
        salary=None,
        work_type=vacancy_domain.WorkTypeEnum.FULL_TIME,
        work_format=[vacancy_domain.WorkFormatEnum.REMOTE],
        is_internship=False,
        is_temphire=False,
        schedule=[],
        daily_rate=[],
        experience=vacancy_domain.ExperienceEnum.EXP_0,
        skills=[Skill(title="python")],
        stages=[vacancy_domain.VacancyStageStatus(stage=vacancy_domain.VacancyStageEnum.SELECTED_AI, shown=True)],
        publication=vacancy_domain.VacancyPublication(
            hh=vacancy_domain.PublicationStatus(state=hh_state, url=None, publication_id=hh_publication_id),
            avito=vacancy_domain.PublicationStatus(
                state=vacancy_domain.PublicationStatusEnum.NOT_PUBLISHED,
                url=None,
                publication_id=None,
            ),
        ),
        statistics=vacancy_domain.VacancyStatistics(total_candidates=0, platform_candidates=0, delegated_candidates=0),
        threshold=0.5,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


@pytest.mark.asyncio
async def test_candidate_polling_v2_run_worker_happy_path_calls_steps_and_sleeps() -> None:
    vacancy = _make_vacancy(
        status=vacancy_domain.VacancyStatus.OPEN,
        hh_state=vacancy_domain.PublicationStatusEnum.PUBLISHED,
        hh_publication_id="123",
    )

    vacancy_service = create_autospec(VacancyService, instance=True, spec_set=True)
    vacancy_service.read_many_published = AsyncMock(return_value=[vacancy])

    hh_vacancy_import_adapter = create_autospec(VacancyImporterProtocol, instance=True, spec_set=True)
    hh_vacancy_import_adapter.import_vacancy_by_id = AsyncMock(
        return_value=VacancyImporterProtocol.ImportVacancyResponse(
            title="t",
            description="d",
            specialization="s",
            status=vacancy_domain.VacancyStatus.OPEN,
            city=None,
            country=None,
            hire_amount=None,
            salary=None,
            work_type=vacancy_domain.WorkTypeEnum.FULL_TIME,
            work_format=[vacancy_domain.WorkFormatEnum.REMOTE],
            is_internship=False,
            is_temphire=False,
            schedule=[],
            daily_rate=[],
            experience=vacancy_domain.ExperienceEnum.EXP_0,
            skills=[Skill(title="python")],
            published_at=datetime.now(UTC),
        )
    )

    svc = HHCandidatePollingV2Service(
        candidate_service=create_autospec(CandidateService, instance=True, spec_set=True),
        llm_service=create_autospec(LLMService, instance=True, spec_set=True),
        user_service=create_autospec(UserService, instance=True, spec_set=True),
        oauth2_service=create_autospec(OAuth2Service, instance=True, spec_set=True),
        vacancy_service=vacancy_service,
        cache=create_autospec(Cache, instance=True, spec_set=True),
        hh_candidate_polling_adapter=create_autospec(CandidatePollingProtocol, instance=True, spec_set=True),
        hh_vacancy_import_adapter=hh_vacancy_import_adapter,
    )

    svc._sleep_between_vacancies_sec = 0  # noqa: SLF001
    svc._sleep_worker_sec = 0  # noqa: SLF001

    poll = AsyncMock(return_value=[])
    analyze = AsyncMock(return_value=0)
    with patch.object(svc, "_poll_new_candidates", poll), patch.object(svc, "_analyze_candidates", analyze):
        sleep = AsyncMock()
        with patch.object(asyncio, "sleep", sleep):
            await svc.run_worker()

    assert vacancy_service.read_many_published.await_count == 1
    assert hh_vacancy_import_adapter.import_vacancy_by_id.await_count == 1
    assert poll.await_count == 1
    assert len(poll.await_args_list) == 1
    poll_req = poll.await_args_list[0].args[0]
    assert poll_req.hh_vacancy_id == "123"
    assert analyze.await_count == 1
    assert sleep.await_count == 2


@pytest.mark.asyncio
async def test_candidate_polling_v2_run_worker_skips_when_hh_not_published() -> None:
    vacancy = _make_vacancy(
        status=vacancy_domain.VacancyStatus.OPEN,
        hh_state=vacancy_domain.PublicationStatusEnum.NOT_PUBLISHED,
        hh_publication_id=None,
    )

    vacancy_service = create_autospec(VacancyService, instance=True, spec_set=True)
    vacancy_service.read_many_published = AsyncMock(return_value=[vacancy])

    hh_vacancy_import_adapter = create_autospec(VacancyImporterProtocol, instance=True, spec_set=True)
    hh_vacancy_import_adapter.import_vacancy_by_id = AsyncMock()

    svc = HHCandidatePollingV2Service(
        candidate_service=create_autospec(CandidateService, instance=True, spec_set=True),
        llm_service=create_autospec(LLMService, instance=True, spec_set=True),
        user_service=create_autospec(UserService, instance=True, spec_set=True),
        oauth2_service=create_autospec(OAuth2Service, instance=True, spec_set=True),
        vacancy_service=vacancy_service,
        cache=create_autospec(Cache, instance=True, spec_set=True),
        hh_candidate_polling_adapter=create_autospec(CandidatePollingProtocol, instance=True, spec_set=True),
        hh_vacancy_import_adapter=hh_vacancy_import_adapter,
    )

    svc._sleep_worker_sec = 0  # noqa: SLF001
    poll = AsyncMock(return_value=[])
    analyze = AsyncMock(return_value=0)
    with patch.object(svc, "_poll_new_candidates", poll), patch.object(svc, "_analyze_candidates", analyze):
        sleep = AsyncMock()
        with patch.object(asyncio, "sleep", sleep):
            await svc.run_worker()

    assert hh_vacancy_import_adapter.import_vacancy_by_id.await_count == 0
    assert poll.await_count == 0
    assert analyze.await_count == 0
    assert sleep.await_count == 1
