from collections.abc import Callable
from datetime import timedelta
from typing import Protocol, overload


class CacheProtocol(Protocol):
    """Protocol defining the interface for cache implementations"""

    @overload
    async def get(self, key: str) -> bytes | None:
        """Retrieve raw bytes data from cache by key.

        Args:
            key: Unique identifier for the cached data.

        Returns:
            The cached bytes value if found, None otherwise.
        """
        ...

    @overload
    async def get[T](
        self,
        key: str,
        *,
        unmarshal_using: Callable[[bytes], T],
    ) -> T | None:
        """Retrieve typed data from cache by key with unmarshalling.

        Args:
            key: Unique identifier for the cached data.
            unmarshal_using: Function to convert bytes to the specified type

        Returns:
            The unmarshalled data of type T if found, None otherwise.
        """
        ...

    @overload
    async def get[T](
        self,
        key: str,
        *,
        unmarshal_as: type[T],
    ) -> T | None:
        """Retrieve typed data from cache by key with unmarshalling.

        Args:
            key: Unique identifier for the cached data.
            unmarshal_as: Type to convert the cached bytes into.

        Returns:
            The unmarshalled data of type T if found, None otherwise.
        """
        ...

    async def get[T](
        self,
        key: str,
        *,
        unmarshal_as: type[T] | None = None,
        unmarshal_using: Callable[[bytes], T] | None = None,
    ) -> T | None:
        """Retrieve data from cache by key with optional unmarshalling.

        This method combines both overloaded versions, allowing for both
        raw bytes retrieval and typed data retrieval.

        Args:
            key: Unique identifier for the cached data.
            unmarshal_as: Optional type to convert the cached bytes into.
                          If None, raw bytes will be returned.
            unmarshal_using: Optional custom function to convert bytes to the specified type.
                             If not provided and unmarshal_as is specified, a default
                             unmarshaller will be used.

        Returns:
            The cached data (either raw bytes or unmarshalled to type T) if found,
            None otherwise.
        """
        ...

    @overload
    async def set(
        self,
        key: str,
        value: bytes,
        *,
        ttl: timedelta | None = None,
    ) -> None:
        """Store raw bytes data in cache.

        Args:
            key: Unique identifier for the cached data.
            value: The bytes data to cache.
            ttl: Optional time-to-live duration. If None, the cache implementation's default TTL will be used.

        Returns:
            None
        """
        ...

    @overload
    async def set[T](
        self,
        key: str,
        value: T,
        *,
        ttl: timedelta | None = None,
        marshal_using: Callable[[T], bytes] | None = None,
    ) -> None:
        """Store typed data in cache with marshalling.

        Args:
            key: Unique identifier for the cached data.
            value: The data of type T to cache.
            ttl: Optional time-to-live duration. If None, the cache implementation's default TTL will be used.
            marshal_using: Optional custom function to convert the data to bytes.
                           If not provided, a default marshaller will be used.

        Returns:
            None
        """
        ...

    async def set[T](
        self,
        key: str,
        value: T,
        *,
        ttl: timedelta | None = None,
        marshal_using: Callable[[T], bytes] | None = None,
    ) -> None:
        """Store data in cache with optional marshalling.

        This method combines both overloaded versions, allowing for both
        raw bytes storage and typed data storage.

        Args:
            key: Unique identifier for the cached data.
            value: The data to cache (either bytes or a typed value).
            ttl: Optional time-to-live duration. If None, the cache implementation's default TTL will be used.
            marshal_using: Optional custom function to convert the data to bytes.
                           If not provided and value is not bytes, a default
                           marshaller will be used.

        Returns:
            None
        """
        ...

    async def delete(self, key: str) -> None:
        """Remove data from cache by key.

        Args:
            key: Unique identifier for the cached data to be deleted.

        Returns:
            None
        """
        ...
