from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import pytest
from dishka import Provider, make_async_container
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.infra.cache import CacheConfig
from hharon.protocols import cache as cache_protocol
from hharon.protocols import oauth2 as oauth2_protocol
from hharon.protocols import outbox_task as outbox_task_protocol
from hharon.protocols import token as token_protocol
from hharon.usecases.crypt import cipher
from hharon.usecases.outbox_task import usecase as outbox_task_usecase
from hharon.usecases.outbox_task.schedulers import token_update_scheduler
from hharon.usecases.token import get_tokens, mark_tokens_invalid, obtain_access_token, refresh_tokens, save_tokens

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.fixture
def token_provider(  # noqa: PLR0913
    base_provider: Provider,
    cipher_usecase: cipher.CipherUsecase,
    mock_token_repository: token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession],
    mock_oauth2_adapter: oauth2_protocol.OAuth2Protocol,
    mock_cache: cache_protocol.CacheProtocol,
    mock_outbox_repository: outbox_task_protocol.OutboxTaskRepositoryProtocol[AsyncSession],
    cache_config: CacheConfig,
) -> Provider:
    """Fixture to create dishka provider with token use case dependencies."""
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
    _ = provider.provide(
        source=staticmethod(lambda: mock_cache),
        provides=cache_protocol.CacheProtocol,
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_outbox_repository),
        provides=outbox_task_protocol.OutboxTaskRepositoryProtocol[AsyncSession],
    )
    _ = provider.provide(
        source=staticmethod(lambda: cache_config),
        provides=CacheConfig,
    )

    return provider


@pytest.fixture
def save_tokens_provider(token_provider: Provider) -> Provider:
    """Fixture to create dishka provider with SaveTokens dependencies."""
    _ = token_provider.provide(source=save_tokens.SaveTokens)
    return token_provider


@pytest.fixture
async def save_tokens_container(save_tokens_provider: Provider) -> AsyncIterator["AsyncContainer"]:
    """Fixture to create dishka container with SaveTokens dependencies."""
    container = make_async_container(save_tokens_provider)
    async with container() as request_container:
        yield request_container
    await container.close()


@pytest.fixture
def get_tokens_provider(token_provider: Provider) -> Provider:
    """Fixture to create dishka provider with GetTokens dependencies."""
    _ = token_provider.provide(source=get_tokens.GetTokens)
    return token_provider


@pytest.fixture
async def get_tokens_container(get_tokens_provider: Provider) -> AsyncIterator["AsyncContainer"]:
    """Fixture to create dishka container with GetTokens dependencies."""
    container = make_async_container(get_tokens_provider)
    async with container() as request_container:
        yield request_container
    await container.close()


@pytest.fixture
def refresh_tokens_provider(
    token_provider: Provider,
    mock_outbox_repository: outbox_task_protocol.OutboxTaskRepositoryProtocol[AsyncSession],
    mock_token_update_scheduler: token_update_scheduler.TokenUpdateScheduler[AsyncSession],
) -> Provider:
    """Fixture to create dishka provider with RefreshTokens dependencies."""
    # Create outbox usecase
    outbox_usecase = outbox_task_usecase.OutboxUsecase[AsyncSession](outbox_repo=mock_outbox_repository)
    _ = token_provider.provide(
        source=staticmethod(lambda: outbox_usecase),
        provides=outbox_task_usecase.OutboxUsecase[AsyncSession],
    )

    # Also provide for the generic class request (tests request OutboxUsecase without type param)
    def provide_outbox_usecase_generic(  # pyright: ignore[reportUnknownParameterType]
        concrete_instance: outbox_task_usecase.OutboxUsecase[AsyncSession],
    ) -> outbox_task_usecase.OutboxUsecase:  # pyright: ignore[reportMissingTypeArgument]
        # Return the concrete instance for dishka compatibility (test mocks)
        return concrete_instance

    _ = token_provider.provide(
        source=provide_outbox_usecase_generic,  # pyright: ignore[reportUnknownArgumentType]
        provides=outbox_task_usecase.OutboxUsecase,
    )

    _ = token_provider.provide(
        source=staticmethod(lambda: mock_token_update_scheduler),
        provides=token_update_scheduler.TokenUpdateScheduler[AsyncSession],
    )

    # Use a factory function to avoid type analysis issues with generic classes
    def provide_refresh_tokens(
        token_repository: token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession],
        hh_oauth2_adapter: oauth2_protocol.OAuth2Protocol,
        cipher_usecase: cipher.CipherUsecase,
        token_update_scheduler: token_update_scheduler.TokenUpdateScheduler[AsyncSession],
    ) -> refresh_tokens.RefreshTokens[AsyncSession]:
        return refresh_tokens.RefreshTokens[AsyncSession](
            token_repository=token_repository,
            hh_oauth2_adapter=hh_oauth2_adapter,
            cipher_usecase=cipher_usecase,
            token_update_scheduler=token_update_scheduler,
        )

    # Provide the concrete type
    _ = token_provider.provide(
        source=provide_refresh_tokens,
        provides=refresh_tokens.RefreshTokens[AsyncSession],
    )

    def provide_refresh_tokens_generic(  # pyright: ignore[reportUnknownParameterType]
        concrete_instance: refresh_tokens.RefreshTokens[AsyncSession],
    ) -> refresh_tokens.RefreshTokens:  # pyright: ignore[reportMissingTypeArgument]
        # Return the concrete instance for dishka compatibility (test mocks)
        return concrete_instance

    _ = token_provider.provide(
        source=provide_refresh_tokens_generic,  # pyright: ignore[reportUnknownArgumentType]
        provides=refresh_tokens.RefreshTokens,
    )
    return token_provider


@pytest.fixture
async def refresh_tokens_container(refresh_tokens_provider: Provider) -> AsyncIterator["AsyncContainer"]:
    """Fixture to create dishka container with RefreshTokens dependencies."""
    container = make_async_container(refresh_tokens_provider)
    async with container() as request_container:
        yield request_container
    await container.close()


@pytest.fixture
def mark_tokens_invalid_provider(token_provider: Provider) -> Provider:
    """Fixture to create dishka provider with MarkTokensInvalid dependencies."""
    _ = token_provider.provide(source=mark_tokens_invalid.MarkTokensInvalid)
    return token_provider


@pytest.fixture
async def mark_tokens_invalid_container(
    mark_tokens_invalid_provider: Provider,
) -> AsyncIterator["AsyncContainer"]:
    """Fixture to create dishka container with MarkTokensInvalid dependencies."""
    container = make_async_container(mark_tokens_invalid_provider)
    async with container() as request_container:
        yield request_container
    await container.close()


@pytest.fixture
def obtain_access_token_provider(token_provider: Provider) -> Provider:
    """Fixture to create dishka provider with ObtainAccessToken dependencies."""
    _ = token_provider.provide(source=obtain_access_token.ObtainAccessToken)
    return token_provider


@pytest.fixture
async def obtain_access_token_container(
    obtain_access_token_provider: Provider,
) -> AsyncIterator["AsyncContainer"]:
    """Fixture to create dishka container with ObtainAccessToken dependencies."""
    container = make_async_container(obtain_access_token_provider)
    async with container() as request_container:
        yield request_container
    await container.close()


@pytest.fixture
async def token_container(token_provider: Provider) -> AsyncIterator["AsyncContainer"]:
    """Fixture to create async container with token use case dependencies."""
    container = make_async_container(token_provider)
    async with container() as request_container:
        yield request_container
    await container.close()
