from datetime import timedelta
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from dishka import Provider, Scope
from sqlalchemy.ext.asyncio import AsyncSession

from hharon import infra
from hharon.adapters.crypt import adapter as cipher_adapter
from hharon.infra.cache import CacheConfig
from hharon.protocols import cache as cache_protocol
from hharon.protocols import oauth2 as oauth2_protocol
from hharon.protocols import outbox_task as outbox_task_protocol
from hharon.protocols import token as token_protocol
from hharon.protocols import user as user_protocol
from hharon.usecases.crypt import cipher
from hharon.usecases.outbox_task.schedulers import token_update_scheduler


@pytest.fixture(scope="session")
def cipher_usecase() -> cipher.CipherUsecase:
    """Fixture to create a real CipherUsecase instance for tests."""
    kp = cipher_adapter.CryptEciesX25519Adapter.generate_keypair()
    adapter = cipher_adapter.CryptEciesX25519Adapter(
        cfg=infra.CryptConfig(private_key_hex=kp.private_hex, public_key_hex=kp.public_hex)
    )
    return cipher.CipherUsecase(crypt_adapter=adapter)


@pytest.fixture
def mock_token_repository() -> token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession]:
    """Fixture to create a mock token repository."""
    return Mock(spec=token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession])


@pytest.fixture
def mock_oauth2_adapter() -> oauth2_protocol.OAuth2Protocol:
    """Fixture to create a mock OAuth2 adapter."""
    return Mock(spec=oauth2_protocol.OAuth2Protocol)


@pytest.fixture
def mock_cache() -> cache_protocol.CacheProtocol:
    """Fixture to create a mock cache."""

    cache = Mock(spec=cache_protocol.CacheProtocol)
    cache.delete = AsyncMock(return_value=None)
    return cache


@pytest.fixture
def mock_outbox_repository() -> outbox_task_protocol.OutboxTaskRepositoryProtocol[AsyncSession]:
    """Fixture to create a mock outbox repository."""
    return Mock(spec=outbox_task_protocol.OutboxTaskRepositoryProtocol[AsyncSession])


@pytest.fixture
def mock_user_repository() -> user_protocol.HharonUserRepositoryProtocol[AsyncSession]:
    """Fixture to create a mock user repository."""
    return Mock(spec=user_protocol.HharonUserRepositoryProtocol[AsyncSession])


@pytest.fixture
def mock_task_handler() -> outbox_task_protocol.TaskHandler[AsyncSession]:
    """Fixture to create a mock TaskHandler with async methods configured."""
    handler = Mock(spec=outbox_task_protocol.TaskHandler[AsyncSession])
    handler.handle = AsyncMock()
    return handler


@pytest.fixture
def mock_token_update_scheduler() -> token_update_scheduler.TokenUpdateScheduler[AsyncSession]:
    """Fixture to create a mock TokenUpdateScheduler with async methods configured."""
    scheduler = Mock(spec=token_update_scheduler.TokenUpdateScheduler[AsyncSession])
    scheduler.schedule = AsyncMock()
    return cast("token_update_scheduler.TokenUpdateScheduler[AsyncSession]", scheduler)


@pytest.fixture
def cache_config() -> CacheConfig:
    """Fixture to create cache config."""
    return CacheConfig(cache_ttl=timedelta(minutes=10))


@pytest.fixture
def base_provider() -> Provider:
    """Base fixture to create a dishka provider."""
    return Provider(scope=Scope.APP)
