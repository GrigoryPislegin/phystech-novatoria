from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from glide import GlideClient

from hharon.adapters.cache.valkey import adapter as valkey_adapter
from hharon.infra.cache import CacheConfig


@pytest.fixture
def mock_glide_client() -> Mock:
    """Create a mock GlideClient for testing."""
    client = Mock(spec=GlideClient)
    client.get = AsyncMock()
    client.set = AsyncMock()
    client.delete = AsyncMock()
    return client


@pytest.fixture
def cache_config() -> CacheConfig:
    """Create a CacheConfig for testing."""
    return CacheConfig(cache_ttl=timedelta(minutes=5))


@pytest.fixture
def valkey_adapter_instance(mock_glide_client: Mock, cache_config: CacheConfig) -> valkey_adapter.ValkeyCacheAdapter:
    """Create a ValkeyCacheAdapter instance for testing."""
    return valkey_adapter.ValkeyCacheAdapter(client=mock_glide_client, config=cache_config)
