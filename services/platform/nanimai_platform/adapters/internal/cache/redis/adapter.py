from datetime import timedelta
from typing import override

from pydantic import RedisDsn
from redis import asyncio as aioredis

from nanimai_platform.protocols.internal import cache as protocol


class RedisCacheAdapter(protocol.CacheProtocol):
    _client: aioredis.Redis
    _default_expire_in: timedelta | None

    def __init__(self, dsn: RedisDsn, default_expire_in: timedelta | None = None):
        self._client = aioredis.from_url(str(dsn))
        self._default_expire_in = default_expire_in

    @override
    async def get(self, key: str) -> str | None:
        try:
            return await self._client.get(key)  # pyright: ignore[reportAny]
        except Exception as e:
            raise protocol.CacheError("failed to get value from cache") from e

    @override
    async def set(self, key: str, value: str, expire_in: timedelta | None = None) -> None:
        try:
            await self._client.set(key, value, ex=expire_in or self._default_expire_in)
        except Exception as e:
            raise protocol.CacheError(f"failed to set value to cache: {e}") from e

    @override
    async def delete(self, key: str) -> None:
        try:
            await self._client.delete(key)
        except Exception as e:
            raise protocol.CacheError(f"failed to delete value from cache: {e}") from e

    @override
    async def clear(self) -> None:
        try:
            await self._client.flushall()
        except Exception as e:
            raise protocol.CacheError(f"failed to clear cache: {e}") from e

    @override
    async def mget(self, keys: list[str]) -> list[str | None]:
        try:
            return await self._client.mget(keys)  # pyright: ignore[reportAny]
        except Exception as e:
            raise protocol.CacheError(f"failed to get values from cache: {e}") from e

    @override
    async def mset(self, mapping: dict[str, str]) -> None:
        try:
            await self._client.mset(mapping)
        except Exception as e:
            raise protocol.CacheError(f"failed to set values to cache: {e}") from e

    @override
    async def sadd(self, key: str, *values: str) -> None:
        try:
            await self._client.sadd(key, *values)  # type: ignore
        except Exception as e:
            raise protocol.CacheError(f"failed to add value to set in cache: {e}") from e

    @override
    async def srem(self, key: str, *values: str) -> None:
        try:
            await self._client.srem(key, *values)  # type: ignore
        except Exception as e:
            raise protocol.CacheError(f"failed to remove value from set in cache: {e}") from e

    @override
    async def sismember(self, key: str, value: str) -> bool:
        try:
            return (await self._client.sismember(key, value)) == 0  # type: ignore
        except Exception as e:
            raise protocol.CacheError(f"failed to check if value is in set in cache: {e}") from e

    @override
    async def smembers(self, key: str) -> list[str]:
        try:
            return await self._client.smembers(key)  # type: ignore
        except Exception as e:
            raise protocol.CacheError(f"failed to get values from set in cache: {e}") from e
