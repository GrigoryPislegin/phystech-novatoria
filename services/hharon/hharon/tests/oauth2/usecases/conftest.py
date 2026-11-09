from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock
from uuid import uuid4

import pytest
from dishka import Provider, make_async_container
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer

from hharon.domain.outbox_task import OutboxTask, OutboxTaskStatus, OutboxTaskType, TokenUpdatePayload
from hharon.domain.scalars import TaskID
from hharon.domain.token import TokenPair
from hharon.domain.user import HharonUser
from hharon.protocols import cache as cache_protocol
from hharon.protocols import oauth2 as oauth2_protocol
from hharon.protocols import token as token_protocol
from hharon.protocols import user as user_protocol
from hharon.usecases.crypt import CipherUsecase, cipher
from hharon.usecases.oauth2 import CompleteOauthFlow, EncryptOAuthState, ExchangeSecretCode, InitOAuthFlow
from hharon.usecases.outbox_task import OutboxUsecase
from hharon.usecases.outbox_task.schedulers import token_update_scheduler


@pytest.fixture
def oauth2_provider(
    base_provider: Provider,
    cipher_usecase: cipher.CipherUsecase,
    mock_oauth2_adapter: oauth2_protocol.OAuth2Protocol,
) -> Provider:
    """Base fixture to create dishka provider with common OAuth2 test dependencies."""
    provider = base_provider
    encrypt_state_usecase = EncryptOAuthState(cipher_usecase=cipher_usecase)

    _ = provider.provide(
        source=staticmethod(lambda: encrypt_state_usecase),
        provides=EncryptOAuthState,
    )
    _ = provider.provide(
        source=staticmethod(lambda: mock_oauth2_adapter),
        provides=oauth2_protocol.OAuth2Protocol,
    )

    return provider


@pytest.fixture
def exchange_secret_code_provider(oauth2_provider: Provider) -> Provider:
    """Fixture to create dishka provider with ExchangeSecretCode dependencies."""
    _ = oauth2_provider.provide(source=ExchangeSecretCode)
    return oauth2_provider


@pytest.fixture
async def exchange_secret_code_container(
    exchange_secret_code_provider: Provider,
) -> AsyncIterator["AsyncContainer"]:
    """Fixture to create dishka container with ExchangeSecretCode dependencies."""
    container = make_async_container(exchange_secret_code_provider)
    async with container() as request_container:
        yield request_container
    await container.close()


@pytest.fixture
def init_oauth_flow_provider(oauth2_provider: Provider) -> Provider:
    """Fixture to create dishka provider with InitOAuthFlow dependencies."""
    _ = oauth2_provider.provide(source=InitOAuthFlow)
    return oauth2_provider


@pytest.fixture
async def init_oauth_flow_container(
    init_oauth_flow_provider: Provider,
) -> AsyncIterator["AsyncContainer"]:
    """Fixture to create dishka container with InitOAuthFlow dependencies."""
    container = make_async_container(init_oauth_flow_provider)
    async with container() as request_container:
        yield request_container
    await container.close()


@pytest.fixture
def mock_exchange_secret_code_usecase() -> ExchangeSecretCode:
    """Fixture to create a mock ExchangeSecretCode usecase."""
    return cast("ExchangeSecretCode", Mock(spec=ExchangeSecretCode))


@pytest.fixture
def mock_oauth2_user_info_adapter() -> oauth2_protocol.OAuth2UserInfoProtocol:
    """Fixture to create a mock OAuth2UserInfoProtocol adapter."""
    return cast("oauth2_protocol.OAuth2UserInfoProtocol", Mock(spec=oauth2_protocol.OAuth2UserInfoProtocol))


@pytest.fixture
def mock_cipher_usecase() -> CipherUsecase:
    """Fixture to create a mock CipherUsecase."""
    return cast("CipherUsecase", Mock(spec=CipherUsecase))


@pytest.fixture
def mock_outbox_usecase() -> OutboxUsecase[AsyncSession]:
    """Fixture to create a mock OutboxUsecase."""
    return cast("OutboxUsecase[AsyncSession]", Mock(spec=OutboxUsecase[AsyncSession]))


@pytest.fixture
def complete_oauth_flow_provider(  # noqa: PLR0913
    oauth2_provider: Provider,
    mock_exchange_secret_code_usecase: ExchangeSecretCode,
    mock_oauth2_user_info_adapter: oauth2_protocol.OAuth2UserInfoProtocol,
    mock_user_repository: user_protocol.HharonUserRepositoryProtocol[AsyncSession],
    mock_token_repository: token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession],
    mock_cipher_usecase: CipherUsecase,
    mock_outbox_usecase: OutboxUsecase[AsyncSession],
    mock_token_update_scheduler: token_update_scheduler.TokenUpdateScheduler[AsyncSession],
    mock_cache: cache_protocol.CacheProtocol,
) -> Provider:
    """Fixture to create dishka provider with CompleteOauthFlow dependencies."""
    _ = oauth2_provider.provide(
        source=staticmethod(lambda: mock_exchange_secret_code_usecase),
        provides=ExchangeSecretCode,
    )
    _ = oauth2_provider.provide(
        source=staticmethod(lambda: mock_oauth2_user_info_adapter),
        provides=oauth2_protocol.OAuth2UserInfoProtocol,
    )
    _ = oauth2_provider.provide(
        source=staticmethod(lambda: mock_user_repository),
        provides=user_protocol.HharonUserRepositoryProtocol[AsyncSession],
    )
    _ = oauth2_provider.provide(
        source=staticmethod(lambda: mock_token_repository),
        provides=token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession],
    )
    _ = oauth2_provider.provide(
        source=staticmethod(lambda: mock_cipher_usecase),
        provides=CipherUsecase,
    )
    _ = oauth2_provider.provide(
        source=staticmethod(lambda: mock_outbox_usecase),
        provides=OutboxUsecase[AsyncSession],
    )
    _ = oauth2_provider.provide(
        source=staticmethod(lambda: mock_token_update_scheduler),
        provides=token_update_scheduler.TokenUpdateScheduler[AsyncSession],
    )
    _ = oauth2_provider.provide(
        source=staticmethod(lambda: mock_cache),
        provides=cache_protocol.CacheProtocol,
    )

    # Use a factory function to avoid type analysis issues with generic classes
    def provide_complete_oauth_flow(  # noqa: PLR0913
        exchange_secret_code_usecase: ExchangeSecretCode,
        hh_user_info_adapter: oauth2_protocol.OAuth2UserInfoProtocol,
        encrypt_state_usecase: EncryptOAuthState,
        user_repository: user_protocol.HharonUserRepositoryProtocol[AsyncSession],
        token_repository: token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession],
        cipher_usecase: CipherUsecase,
        token_update_scheduler: token_update_scheduler.TokenUpdateScheduler[AsyncSession],
        cache: cache_protocol.CacheProtocol,
    ) -> CompleteOauthFlow[AsyncSession]:
        return CompleteOauthFlow[AsyncSession](
            exchange_secret_code_usecase=exchange_secret_code_usecase,
            hh_user_info_adapter=hh_user_info_adapter,
            encrypt_state_usecase=encrypt_state_usecase,
            user_repository=user_repository,
            token_repository=token_repository,
            cipher_usecase=cipher_usecase,
            token_update_scheduler=token_update_scheduler,
            cache=cache,
        )

    _ = oauth2_provider.provide(source=provide_complete_oauth_flow)

    return oauth2_provider


@pytest.fixture
async def complete_oauth_flow_container(
    complete_oauth_flow_provider: Provider,
) -> AsyncIterator["AsyncContainer"]:
    """Fixture to create dishka container with CompleteOauthFlow dependencies."""
    container = make_async_container(complete_oauth_flow_provider)
    async with container() as request_container:
        yield request_container
    await container.close()


@pytest.fixture
def mock_exchange_secret_code_response() -> ExchangeSecretCode.ExchangeSecretCodeResponse:
    """Fixture to create a mock ExchangeSecretCode response."""
    return ExchangeSecretCode.ExchangeSecretCodeResponse(
        access_token="test_access_token",  # noqa: S106
        refresh_token="test_refresh_token",  # noqa: S106
        expires_in=3600,
    )


@pytest.fixture
def mock_user_info_response() -> oauth2_protocol.OAuth2UserInfoProtocol.GetCurrentUserInfoResponse:
    """Fixture to create a mock OAuth2UserInfoProtocol response."""
    return oauth2_protocol.OAuth2UserInfoProtocol.GetCurrentUserInfoResponse(
        hh_manager_id="123456",
        hh_employer_id="654321",
        name="John Doe",
        email="john@example.com",
    )


@pytest.fixture
def mock_created_user() -> HharonUser:
    """Fixture to create a mock HharonUser."""
    return HharonUser(
        user_id="507f1f77bcf86cd799439011",
        hh_manager_id="123456",
        hh_employer_id="654321",
        name="John Doe",
        email="john@example.com",
    )


@pytest.fixture
def mock_token_pair(mock_created_user: HharonUser) -> TokenPair:
    """Fixture to create a mock TokenPair."""
    return TokenPair(
        user_id=mock_created_user.user_id,
        encrypted_access_token=b"encrypted_access",
        encrypted_refresh_token=b"encrypted_refresh",
        expires_at=datetime.now(UTC) + timedelta(seconds=3600),
        token_type="bearer",  # noqa: S106
    )


@pytest.fixture
def mock_outbox_task(mock_created_user: HharonUser) -> OutboxTask:
    """Fixture to create a mock OutboxTask."""
    payload = TokenUpdatePayload(user_id=mock_created_user.user_id)
    return OutboxTask(
        id=TaskID.from_uuid(uuid4()),
        task_type=OutboxTaskType.TOKEN_UPDATE,
        payload=payload.model_dump(mode="json"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        available_at=datetime.now(UTC) + timedelta(seconds=3600),
        attempts=0,
        status=OutboxTaskStatus.PENDING,
    )
