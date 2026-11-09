from collections.abc import AsyncIterator
from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest
from dishka import Provider, make_async_container
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.infra.resume_search_scan import ResumeSearchScanConfig, ResumeSearchScanInitialDelayConstant
from hharon.protocols import outbox_task as outbox_task_protocol
from hharon.protocols import resume_search_scan as resume_search_scan_protocol
from hharon.usecases import resume_search_scan
from hharon.usecases.outbox_task import usecase as outbox_task_usecase

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.fixture
def setup_resume_search_scan_provider(
    base_provider: Provider,
    mock_resume_search_scan_repository: resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol[AsyncSession],
    mock_outbox_repository: outbox_task_protocol.OutboxTaskRepositoryProtocol[AsyncSession],
) -> Provider:
    """Fixture to create dishka provider with
    InitSearchCampaignExecution and CompleteSearchCampaignExecution dependencies."""
    provider = base_provider

    _ = provider.provide(
        source=staticmethod(lambda: mock_resume_search_scan_repository),
        provides=resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol[AsyncSession],
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_outbox_repository),
        provides=outbox_task_protocol.OutboxTaskRepositoryProtocol[AsyncSession],
    )

    outbox_usecase = outbox_task_usecase.OutboxUsecase[AsyncSession](outbox_repo=mock_outbox_repository)
    _ = provider.provide(
        source=staticmethod(lambda: outbox_usecase),
        provides=outbox_task_usecase.OutboxUsecase[AsyncSession],
    )

    config = ResumeSearchScanConfig(
        scans_per_day=3,
        initial_delay=ResumeSearchScanInitialDelayConstant(value=timedelta(minutes=1)),
    )
    setup_usecase = resume_search_scan.InitSearchCampaignExecution[AsyncSession](
        resume_search_scan_repository=mock_resume_search_scan_repository,
        outbox_usecase=outbox_usecase,
        config=config,
    )
    _ = provider.provide(
        source=staticmethod(lambda: setup_usecase),
        provides=resume_search_scan.InitSearchCampaignExecution[AsyncSession],
    )

    complete_usecase = resume_search_scan.CompleteSearchCampaignExecution[AsyncSession](
        resume_search_scan_repository=mock_resume_search_scan_repository,
    )
    _ = provider.provide(
        source=staticmethod(lambda: complete_usecase),
        provides=resume_search_scan.CompleteSearchCampaignExecution[AsyncSession],
    )

    return provider


@pytest.fixture
async def setup_resume_search_scan_container(
    setup_resume_search_scan_provider: Provider,
) -> AsyncIterator["AsyncContainer"]:
    """Fixture to create dishka container with
    InitSearchCampaignExecution and CompleteSearchCampaignExecution dependencies."""
    container = make_async_container(setup_resume_search_scan_provider)
    async with container() as request_container:
        yield request_container
    await container.close()


@pytest.fixture
def mock_resume_search_scan_repository() -> Mock:
    """Create a mock ResumeSearchScanRepositoryProtocol."""
    repo = Mock(spec=resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol[AsyncSession])
    repo.context = AsyncMock()
    return repo
