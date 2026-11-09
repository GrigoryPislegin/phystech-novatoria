from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock

import pytest
from dishka import Provider, make_async_container
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.infra.token_update import TokenUpdateConfig
from hharon.protocols import oauth2 as oauth2_protocol
from hharon.protocols import token as token_protocol
from hharon.protocols.outbox_task.protocol import OutboxTaskRepositoryProtocol
from hharon.usecases.crypt import cipher
from hharon.usecases.outbox_task.handlers import token_update_handler
from hharon.usecases.outbox_task.schedulers import token_update_scheduler
from hharon.usecases.token import refresh_tokens

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.fixture
def token_update_handler_provider(
    base_provider: Provider,
    cipher_usecase: cipher.CipherUsecase,
    mock_token_repository: token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession],
    mock_oauth2_adapter: oauth2_protocol.OAuth2Protocol,
    mock_outbox_repository: OutboxTaskRepositoryProtocol[AsyncSession],
) -> Provider:
    """Fixture to create dishka provider with TokenUpdateHandler dependencies."""

    provider = base_provider

    _ = provider.provide(
        source=staticmethod(lambda: cipher_usecase),
        provides=cipher.CipherUsecase,
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_token_repository),
        provides=token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession],
    )
    # Also provide without type parameter for tests that request it directly
    _ = provider.provide(
        source=staticmethod(lambda: mock_token_repository),
        provides=token_protocol.HeadHunterTokenRepositoryProtocol,
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_oauth2_adapter),
        provides=oauth2_protocol.OAuth2Protocol,
    )
    # Create mock scheduler
    mock_scheduler = Mock(spec=token_update_scheduler.TokenUpdateScheduler[AsyncSession])
    mock_scheduler.schedule = AsyncMock()
    _ = provider.provide(
        source=staticmethod(lambda: mock_scheduler),
        provides=token_update_scheduler.TokenUpdateScheduler[AsyncSession],
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_outbox_repository),
        provides=OutboxTaskRepositoryProtocol[AsyncSession],
    )

    refresh_tokens_usecase = refresh_tokens.RefreshTokens[AsyncSession](
        token_repository=mock_token_repository,
        hh_oauth2_adapter=mock_oauth2_adapter,
        cipher_usecase=cipher_usecase,
        token_update_scheduler=cast("token_update_scheduler.TokenUpdateScheduler[AsyncSession]", mock_scheduler),
    )
    _ = provider.provide(
        source=staticmethod(lambda: refresh_tokens_usecase),
        provides=refresh_tokens.RefreshTokens[AsyncSession],
    )

    # Create handler
    handler = token_update_handler.TokenUpdateHandler[AsyncSession](
        token_repository=mock_token_repository,
        refresh_tokens_usecase=refresh_tokens_usecase,
        token_update_scheduler=cast("token_update_scheduler.TokenUpdateScheduler[AsyncSession]", mock_scheduler),
        config=TokenUpdateConfig(max_retries=3),
        outbox_repo=mock_outbox_repository,
    )
    _ = provider.provide(
        source=staticmethod(lambda: handler),
        provides=token_update_handler.TokenUpdateHandler[AsyncSession],
    )

    return provider


@pytest.fixture
async def token_update_handler_container(
    token_update_handler_provider: Provider,
) -> AsyncIterator["AsyncContainer"]:
    """Fixture to create dishka container with TokenUpdateHandler dependencies."""
    container = make_async_container(token_update_handler_provider)
    async with container() as request_container:
        yield request_container
    await container.close()


@pytest.fixture
def mock_outbox_repository() -> Mock:
    """Create a mock OutboxTaskRepositoryProtocol."""
    repo = Mock(spec=OutboxTaskRepositoryProtocol[AsyncSession])
    repo.context = AsyncMock()
    return repo
