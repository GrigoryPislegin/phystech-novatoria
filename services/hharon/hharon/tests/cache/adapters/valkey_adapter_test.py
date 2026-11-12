# pyright: reportAny=false, reportUnknownVariableType=false
from datetime import timedelta
from unittest.mock import Mock

import pytest
from glide import ExpirySet, ExpiryType

from hharon.adapters.cache.valkey import adapter as valkey_adapter
from hharon.infra.cache import CacheConfig


@pytest.mark.asyncio
async def test_get_returns_bytes_when_no_unmarshal(
    valkey_adapter_instance: valkey_adapter.ValkeyCacheAdapter, mock_glide_client: Mock
) -> None:
    """Test that get returns raw bytes when no unmarshal options are provided."""
    test_key = "test_key"
    test_value = b"test_value"
    mock_glide_client.get.return_value = test_value

    result = await valkey_adapter_instance.get(test_key)

    assert result == test_value
    mock_glide_client.get.assert_awaited_once_with(test_key)


@pytest.mark.asyncio
async def test_get_returns_none_when_key_not_found(
    valkey_adapter_instance: valkey_adapter.ValkeyCacheAdapter, mock_glide_client: Mock
) -> None:
    """Test that get returns None when key is not found."""
    test_key = "nonexistent_key"
    mock_glide_client.get.return_value = None

    result = await valkey_adapter_instance.get(test_key)

    assert result is None
    mock_glide_client.get.assert_awaited_once_with(test_key)


@pytest.mark.asyncio
async def test_get_unmarshals_with_unmarshal_as(
    valkey_adapter_instance: valkey_adapter.ValkeyCacheAdapter, mock_glide_client: Mock
) -> None:
    """Test that get unmarshals data using unmarshal_as parameter."""
    test_key = "test_key"
    test_data = {"name": "test", "value": 123}
    serialized_data = b'{"name":"test","value":123}'
    mock_glide_client.get.return_value = serialized_data

    result: dict[str, str | int] | None = await valkey_adapter_instance.get(test_key, unmarshal_as=dict)

    assert isinstance(result, dict)
    assert result == test_data
    mock_glide_client.get.assert_awaited_once_with(test_key)


@pytest.mark.asyncio
async def test_get_unmarshals_with_unmarshal_using(
    valkey_adapter_instance: valkey_adapter.ValkeyCacheAdapter, mock_glide_client: Mock
) -> None:
    """Test that get unmarshals data using unmarshal_using parameter."""
    test_key = "test_key"
    test_value = b"test_bytes"

    def custom_unmarshal(data: bytes) -> str:
        return data.decode("utf-8").upper()

    mock_glide_client.get.return_value = test_value

    result = await valkey_adapter_instance.get(test_key, unmarshal_using=custom_unmarshal)

    assert result == "TEST_BYTES"
    mock_glide_client.get.assert_awaited_once_with(test_key)


@pytest.mark.asyncio
async def test_get_returns_none_on_exception(
    valkey_adapter_instance: valkey_adapter.ValkeyCacheAdapter, mock_glide_client: Mock
) -> None:
    """Test that get returns None when an exception occurs."""
    test_key = "test_key"
    mock_glide_client.get.side_effect = Exception("Connection error")

    result = await valkey_adapter_instance.get(test_key)

    assert result is None
    mock_glide_client.get.assert_awaited_once_with(test_key)


@pytest.mark.asyncio
async def test_set_stores_bytes_with_default_ttl(
    valkey_adapter_instance: valkey_adapter.ValkeyCacheAdapter, mock_glide_client: Mock, cache_config: CacheConfig
) -> None:
    """Test that set stores bytes using default TTL from config."""
    test_key = "test_key"
    test_value = b"test_value"
    expected_expiry = ExpirySet(ExpiryType.SEC, int(cache_config.cache_ttl.total_seconds()))

    await valkey_adapter_instance.set(test_key, test_value)

    mock_glide_client.set.assert_awaited_once_with(test_key, test_value, expiry=expected_expiry)


@pytest.mark.asyncio
async def test_set_stores_bytes_with_custom_ttl(
    valkey_adapter_instance: valkey_adapter.ValkeyCacheAdapter, mock_glide_client: Mock
) -> None:
    """Test that set stores bytes using custom TTL."""
    test_key = "test_key"
    test_value = b"test_value"
    custom_ttl = timedelta(minutes=15)
    expected_expiry = ExpirySet(ExpiryType.SEC, int(custom_ttl.total_seconds()))

    await valkey_adapter_instance.set(test_key, test_value, ttl=custom_ttl)

    mock_glide_client.set.assert_awaited_once_with(test_key, test_value, expiry=expected_expiry)


@pytest.mark.asyncio
async def test_set_serializes_value_with_marshal_using(
    valkey_adapter_instance: valkey_adapter.ValkeyCacheAdapter, mock_glide_client: Mock, cache_config: CacheConfig
) -> None:
    """Test that set serializes value using marshal_using parameter."""
    test_key = "test_key"
    test_value: dict[str, str | int] = {"name": "test", "value": 123}

    def custom_marshal(value: dict[str, str | int]) -> bytes:
        return str(value).encode("utf-8")

    expected_bytes = custom_marshal(test_value)
    expected_expiry = ExpirySet(ExpiryType.SEC, int(cache_config.cache_ttl.total_seconds()))

    await valkey_adapter_instance.set(test_key, test_value, marshal_using=custom_marshal)

    mock_glide_client.set.assert_awaited_once_with(test_key, expected_bytes, expiry=expected_expiry)


@pytest.mark.asyncio
async def test_set_serializes_value_with_default_serializer(
    valkey_adapter_instance: valkey_adapter.ValkeyCacheAdapter, mock_glide_client: Mock, cache_config: CacheConfig
) -> None:
    """Test that set serializes value using default serializer when marshal_using is not provided."""
    test_key = "test_key"
    test_value = {"name": "test", "value": 123}
    expected_expiry = ExpirySet(ExpiryType.SEC, int(cache_config.cache_ttl.total_seconds()))

    await valkey_adapter_instance.set(test_key, test_value)

    call_args = mock_glide_client.set.await_args
    assert call_args is not None
    assert call_args[0][0] == test_key
    assert isinstance(call_args[0][1], bytes)
    assert call_args[1]["expiry"] == expected_expiry


@pytest.mark.asyncio
async def test_set_handles_exception_gracefully(
    valkey_adapter_instance: valkey_adapter.ValkeyCacheAdapter, mock_glide_client: Mock
) -> None:
    """Test that set handles exceptions gracefully without raising."""
    test_key = "test_key"
    test_value = b"test_value"
    mock_glide_client.set.side_effect = Exception("Connection error")

    # Should not raise exception
    await valkey_adapter_instance.set(test_key, test_value)

    mock_glide_client.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_removes_key(
    valkey_adapter_instance: valkey_adapter.ValkeyCacheAdapter, mock_glide_client: Mock
) -> None:
    """Test that delete removes key from cache."""
    test_key = "test_key"
    mock_glide_client.delete.return_value = None

    await valkey_adapter_instance.delete(test_key)

    mock_glide_client.delete.assert_awaited_once_with([test_key])


@pytest.mark.asyncio
async def test_delete_handles_exception_gracefully(
    valkey_adapter_instance: valkey_adapter.ValkeyCacheAdapter, mock_glide_client: Mock
) -> None:
    """Test that delete handles exceptions gracefully without raising."""
    test_key = "test_key"
    mock_glide_client.delete.side_effect = Exception("Connection error")

    # Should not raise exception
    await valkey_adapter_instance.delete(test_key)

    mock_glide_client.delete.assert_awaited_once_with([test_key])


@pytest.mark.asyncio
async def test_get_with_unmarshal_as_handles_deserialization_error(
    valkey_adapter_instance: valkey_adapter.ValkeyCacheAdapter, mock_glide_client: Mock
) -> None:
    """Test that get handles deserialization errors gracefully."""
    test_key = "test_key"
    invalid_data = b"invalid_json_data"
    mock_glide_client.get.return_value = invalid_data

    # Should return None when deserialization fails
    result: dict[str, str | int] | None = await valkey_adapter_instance.get(test_key, unmarshal_as=dict)

    # The adapter should catch the exception and return None
    assert result is None
