from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from dishka import Provider, make_async_container
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.domain.outbox_task import OutboxTask, OutboxTaskStatus, OutboxTaskType, ResponseCollectionPayload
from hharon.domain.scalars import ResponseCollectionSettingsID, TaskID
from hharon.infra.config import ResponseCollectionConfig
from hharon.infra.headhunter import HeadHunterClient
from hharon.protocols import outbox_task as outbox_task_protocol
from hharon.protocols import response_collection as response_collection_protocol
from hharon.protocols import token as token_protocol
from hharon.protocols.outbox_task.protocol import OutboxTaskRepositoryProtocol
from hharon.usecases import ExperienceFormatter, ResumeFormatter
from hharon.usecases.message_queue import MessageQueuePushUsecase
from hharon.usecases.outbox_task import usecase as outbox_task_usecase
from hharon.usecases.outbox_task.handlers import response_collection_handler
from hharon.usecases.token import get_tokens

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer

    from hharon.usecases.crypt import cipher


@pytest.fixture
def response_collection_handler_provider(  # noqa: PLR0913
    base_provider: Provider,
    cipher_usecase: "cipher.CipherUsecase",
    mock_response_collection_repository: response_collection_protocol.ResponseCollectionRepositoryProtocol[
        AsyncSession
    ],
    mock_token_repository: token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession],
    mock_hh_client: response_collection_protocol.ResponseCollectionHHApiProtocol,
    mock_outbox_repository: outbox_task_protocol.OutboxTaskRepositoryProtocol[AsyncSession],
) -> Provider:
    """Fixture to create dishka provider with ResponseCollectionHandler dependencies."""

    provider = base_provider

    _ = provider.provide(
        source=staticmethod(lambda: mock_response_collection_repository),
        provides=response_collection_protocol.ResponseCollectionRepositoryProtocol[AsyncSession],
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_token_repository),
        provides=token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession],
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_hh_client),
        provides=response_collection_protocol.ResponseCollectionHHApiProtocol,
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_outbox_repository),
        provides=outbox_task_protocol.OutboxTaskRepositoryProtocol[AsyncSession],
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_outbox_repository),
        provides=OutboxTaskRepositoryProtocol[AsyncSession],
    )

    # Create outbox usecase
    outbox_usecase = outbox_task_usecase.OutboxUsecase[AsyncSession](outbox_repo=mock_outbox_repository)
    _ = provider.provide(
        source=staticmethod(lambda: outbox_usecase),
        provides=outbox_task_usecase.OutboxUsecase[AsyncSession],
    )

    # Create get_tokens usecase

    get_tokens_usecase = get_tokens.GetTokens(
        token_repository=mock_token_repository,
        cipher_usecase=cipher_usecase,
    )
    _ = provider.provide(
        source=staticmethod(lambda: get_tokens_usecase),
        provides=get_tokens.GetTokens,
    )

    # Create config
    config = ResponseCollectionConfig(max_responses_per_session=300, max_retries=5)
    _ = provider.provide(
        source=staticmethod(lambda: config),
        provides=ResponseCollectionConfig,
    )

    # Create handler
    handler = response_collection_handler.ResponseCollectionHandler[AsyncSession](
        response_collection_repository=mock_response_collection_repository,
        token_repository=mock_token_repository,
        get_tokens_usecase=get_tokens_usecase,
        hh_client=mock_hh_client,
        outbox_usecase=outbox_usecase,
        outbox_repo=mock_outbox_repository,
        config=config,
        message_queue=cast("MessageQueuePushUsecase", AsyncMock(MessageQueuePushUsecase)),
        formatter=ResumeFormatter(ExperienceFormatter()),
    )
    _ = provider.provide(
        source=staticmethod(lambda: handler),
        provides=response_collection_handler.ResponseCollectionHandler[AsyncSession],
    )

    return provider


@pytest.fixture
async def response_collection_handler_container(
    response_collection_handler_provider: Provider,
) -> AsyncIterator["AsyncContainer"]:
    """Fixture to create dishka container with ResponseCollectionHandler dependencies."""
    container = make_async_container(response_collection_handler_provider)
    async with container() as request_container:
        yield request_container
    await container.close()


@pytest.fixture
def mock_response_collection_repository() -> Mock:
    """Create a mock ResponseCollectionRepositoryProtocol."""
    repo = Mock(spec=response_collection_protocol.ResponseCollectionRepositoryProtocol[AsyncSession])
    repo.context = AsyncMock()
    return repo


@pytest.fixture
def mock_hh_client() -> Mock:
    """Create a mock HeadHunterClient."""
    return Mock(spec=HeadHunterClient)


@pytest.fixture
def mock_outbox_repository() -> Mock:
    """Create a mock OutboxTaskRepositoryProtocol."""
    repo = Mock(spec=outbox_task_protocol.OutboxTaskRepositoryProtocol[AsyncSession])
    repo.context = AsyncMock()
    return repo


@pytest.fixture
def mock_task() -> OutboxTask:
    """Create a mock OutboxTask for testing."""
    settings_id = ResponseCollectionSettingsID()
    payload = ResponseCollectionPayload(settings_id=settings_id)
    now = datetime.now(UTC)
    return OutboxTask(
        id=TaskID.from_uuid(uuid4()),
        task_type=OutboxTaskType.RESPONSE_COLLECTION,
        payload=payload.model_dump(mode="json"),
        created_at=now,
        updated_at=now,
        available_at=now,
        attempts=0,
        status=OutboxTaskStatus.PENDING,
    )
