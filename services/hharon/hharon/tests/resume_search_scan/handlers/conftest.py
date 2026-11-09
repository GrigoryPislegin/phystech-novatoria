from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from dishka import Provider, make_async_container
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.domain.outbox_task import OutboxTask, OutboxTaskStatus, OutboxTaskType, ResumeSearchScanPayload
from hharon.domain.scalars import SearchCampaignID, TaskID
from hharon.infra.resume_search_scan import ResumeSearchScanConfig, ResumeSearchScanInitialDelayConstant
from hharon.protocols import outbox_task as outbox_task_protocol
from hharon.protocols import resume_search_scan as resume_search_scan_protocol
from hharon.protocols import token as token_protocol
from hharon.protocols.outbox_task.protocol import OutboxTaskRepositoryProtocol
from hharon.usecases import ExperienceFormatter
from hharon.usecases.message_queue import MessageQueuePushUsecase
from hharon.usecases.outbox_task import usecase as outbox_task_usecase
from hharon.usecases.outbox_task.handlers import resume_search_scan_handler
from hharon.usecases.resume_formatter.resume_formatter import ResumeFormatter
from hharon.usecases.resume_search_scan.complete_usecase import CompleteSearchCampaignExecution
from hharon.usecases.token import get_tokens

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer

    from hharon.usecases.crypt import cipher


@pytest.fixture
def resume_search_scan_handler_provider(  # noqa: PLR0913
    base_provider: Provider,
    cipher_usecase: "cipher.CipherUsecase",
    mock_resume_search_scan_repository: resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol[AsyncSession],
    mock_token_repository: token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession],
    mock_hh_resume_search_scan_client: resume_search_scan_protocol.ResumeSearchScanHHApiProtocol,
    mock_outbox_repository: outbox_task_protocol.OutboxTaskRepositoryProtocol[AsyncSession],
) -> Provider:
    """Fixture to create dishka provider with ResumeSearchScanHandler dependencies."""
    provider = base_provider

    _ = provider.provide(
        source=staticmethod(lambda: mock_resume_search_scan_repository),
        provides=resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol[AsyncSession],
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_token_repository),
        provides=token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession],
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_hh_resume_search_scan_client),
        provides=resume_search_scan_protocol.ResumeSearchScanHHApiProtocol,
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_outbox_repository),
        provides=outbox_task_protocol.OutboxTaskRepositoryProtocol[AsyncSession],
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_outbox_repository),
        provides=OutboxTaskRepositoryProtocol[AsyncSession],
    )

    outbox_usecase = outbox_task_usecase.OutboxUsecase[AsyncSession](outbox_repo=mock_outbox_repository)
    _ = provider.provide(
        source=staticmethod(lambda: outbox_usecase),
        provides=outbox_task_usecase.OutboxUsecase[AsyncSession],
    )

    get_tokens_usecase = get_tokens.GetTokens(
        token_repository=mock_token_repository,
        cipher_usecase=cipher_usecase,
    )
    _ = provider.provide(
        source=staticmethod(lambda: get_tokens_usecase),
        provides=get_tokens.GetTokens,
    )

    config = ResumeSearchScanConfig(
        scans_per_day=3,
        max_retries=5,
        initial_delay=ResumeSearchScanInitialDelayConstant(value=timedelta(minutes=1)),
    )
    _ = provider.provide(
        source=staticmethod(lambda: config),
        provides=ResumeSearchScanConfig,
    )

    complete_usecase = CompleteSearchCampaignExecution[AsyncSession](
        resume_search_scan_repository=mock_resume_search_scan_repository,
    )
    _ = provider.provide(
        source=staticmethod(lambda: complete_usecase),
        provides=CompleteSearchCampaignExecution[AsyncSession],
    )

    handler = resume_search_scan_handler.ResumeSearchScanHandler[AsyncSession](
        resume_search_scan_repository=mock_resume_search_scan_repository,
        token_repository=mock_token_repository,
        get_tokens_usecase=get_tokens_usecase,
        hh_client=mock_hh_resume_search_scan_client,
        outbox_usecase=outbox_usecase,
        outbox_repo=mock_outbox_repository,
        config=config,
        message_queue=cast("MessageQueuePushUsecase", Mock(spec=MessageQueuePushUsecase)),
        formatter=ResumeFormatter(ExperienceFormatter()),
        complete_search_campaign_usecase=complete_usecase,
    )
    _ = provider.provide(
        source=staticmethod(lambda: handler),
        provides=resume_search_scan_handler.ResumeSearchScanHandler[AsyncSession],
    )

    return provider


@pytest.fixture
async def resume_search_scan_handler_container(
    resume_search_scan_handler_provider: Provider,
) -> AsyncIterator["AsyncContainer"]:
    """Fixture to create dishka container with ResumeSearchScanHandler dependencies."""
    container = make_async_container(resume_search_scan_handler_provider)
    async with container() as request_container:
        yield request_container
    await container.close()


@pytest.fixture
def mock_resume_search_scan_repository() -> Mock:
    """Create a mock ResumeSearchScanRepositoryProtocol."""
    repo = Mock(spec=resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol[AsyncSession])
    repo.context = AsyncMock()
    return repo


@pytest.fixture
def mock_hh_resume_search_scan_client() -> Mock:
    """Create a mock ResumeSearchScanHHApiProtocol."""
    return Mock(spec=resume_search_scan_protocol.ResumeSearchScanHHApiProtocol)


@pytest.fixture
def mock_outbox_repository() -> Mock:
    """Create a mock OutboxTaskRepositoryProtocol."""
    repo = Mock(spec=outbox_task_protocol.OutboxTaskRepositoryProtocol[AsyncSession])
    repo.context = AsyncMock()
    return repo


@pytest.fixture
def mock_resume_search_scan_task() -> OutboxTask:
    """Create a mock OutboxTask for ResumeSearchScan testing."""
    campaign_id = SearchCampaignID()

    payload = ResumeSearchScanPayload(campaign_id=campaign_id)
    now = datetime.now(UTC)
    return OutboxTask(
        id=TaskID.from_uuid(uuid4()),
        task_type=OutboxTaskType.RESUME_SEARCH_SCAN,
        payload=payload.model_dump(mode="json"),
        created_at=now,
        updated_at=now,
        available_at=now,
        attempts=0,
        status=OutboxTaskStatus.PENDING,
    )
