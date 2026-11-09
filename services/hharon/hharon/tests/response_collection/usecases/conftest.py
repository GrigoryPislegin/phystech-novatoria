from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest
from dishka import Provider, make_async_container
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.protocols import outbox_task as outbox_task_protocol
from hharon.protocols import response_collection as response_collection_protocol
from hharon.usecases import response_collection
from hharon.usecases.outbox_task import usecase as outbox_task_usecase

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.fixture
def setup_response_collection_provider(
    base_provider: Provider,
    mock_response_collection_repository: response_collection_protocol.ResponseCollectionRepositoryProtocol[
        AsyncSession
    ],
    mock_outbox_repository: outbox_task_protocol.OutboxTaskRepositoryProtocol[AsyncSession],
) -> Provider:
    """Fixture to create dishka provider with InitResponseCollection dependencies."""

    provider = base_provider

    _ = provider.provide(
        source=staticmethod(lambda: mock_response_collection_repository),
        provides=response_collection_protocol.ResponseCollectionRepositoryProtocol[AsyncSession],
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_outbox_repository),
        provides=outbox_task_protocol.OutboxTaskRepositoryProtocol[AsyncSession],
    )

    # Create outbox usecase
    outbox_usecase = outbox_task_usecase.OutboxUsecase[AsyncSession](outbox_repo=mock_outbox_repository)
    _ = provider.provide(
        source=staticmethod(lambda: outbox_usecase),
        provides=outbox_task_usecase.OutboxUsecase[AsyncSession],
    )

    # Create setup usecase
    setup_usecase = response_collection.InitResponseCollection[AsyncSession](
        _response_collection_repository=mock_response_collection_repository,
        _outbox_usecase=outbox_usecase,
    )
    _ = provider.provide(
        source=staticmethod(lambda: setup_usecase),
        provides=response_collection.InitResponseCollection[AsyncSession],
    )

    return provider


@pytest.fixture
async def setup_response_collection_container(
    setup_response_collection_provider: Provider,
) -> AsyncIterator["AsyncContainer"]:
    """Fixture to create dishka container with InitResponseCollection dependencies."""
    container = make_async_container(setup_response_collection_provider)
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
def mock_outbox_repository() -> Mock:
    """Create a mock OutboxTaskRepositoryProtocol."""
    repo = Mock(spec=outbox_task_protocol.OutboxTaskRepositoryProtocol[AsyncSession])
    repo.context = AsyncMock()
    return repo
