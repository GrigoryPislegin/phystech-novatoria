import base64
import json
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any, TypeVar, overload

import pydantic
import structlog

from nanimai_platform.protocols.internal.cache.protocol import CacheProtocol
from nanimai_platform.services.cache.keyspace import Key
from nanimai_platform.utils.logging_span import span

T = TypeVar("T", bound=pydantic.BaseModel)

logger = structlog.stdlib.get_logger("app.service.Cache")


class Cache:
    DEFAULT = timedelta(minutes=10)

    def __init__(self, adapter: CacheProtocol):
        self._adapter = adapter

    @overload
    async def get(
        self,
        key: Key,
        *,
        t: None = None,
        silent: bool = True,
    ) -> dict[str, Any] | None: ...

    @overload
    async def get(
        self,
        key: Key,
        *,
        t: type[T],
        silent: bool = True,
    ) -> T | None: ...

    @span(op="cache_service", name="get")
    async def get(
        self,
        key: Key,
        *,
        t: type[T] | None = None,
        silent: bool = True,
    ) -> T | dict[str, Any] | None:
        try:
            value = await self._adapter.get(key.as_str())
            if value is None:
                return None
            value = self._b64d(value)

            if t is None:
                return json.loads(value)

            return t.model_validate_json(value)
        except Exception as e:
            if not silent:
                raise e
            else:
                logger.warning("failed to get value from cache", key=key.as_str(), error=str(e))
                return None

    @span(op="cache_service", name="set")
    async def set(
        self,
        key: Key,
        value: pydantic.BaseModel | dict[str, Any],
        *,
        expire: timedelta | None = None,
        silent: bool = True,
    ):
        if expire is None:
            expire = self.DEFAULT

        try:
            if isinstance(value, dict):
                value_json = json.dumps(value)
            else:
                value_json = value.model_dump_json()
            value_json = self._b64e(value_json)

            await self._adapter.set(key.as_str(), value_json, expire_in=expire)
        except Exception as e:
            if not silent:
                raise e
            else:
                logger.warning("failed to set value to cache", key=key.as_str(), error=str(e))
                return None

    @span(op="cache_service", name="invalidate")
    async def invalidate(self, key: Key, silent: bool = True):
        try:
            await self._adapter.delete(key.as_str())
        except Exception as e:
            if not silent:
                raise e
            else:
                logger.warning("failed to invalidate cache", key=key.as_str(), error=str(e))
                return None

    @overload
    async def mget(
        self,
        keys: Sequence[Key],
        *,
        t: None = None,
        silent: bool = True,
    ) -> Sequence[dict[str, Any] | None]: ...

    @overload
    async def mget(
        self,
        keys: Sequence[Key],
        *,
        t: type[T],
        silent: bool = True,
    ) -> Sequence[T | None]: ...

    @span(op="cache_service", name="mget")
    async def mget(
        self,
        keys: Sequence[Key],
        *,
        t: type[T] | None = None,
        silent: bool = True,
    ) -> Sequence[T | dict[str, Any] | None]:
        try:
            values = await self._adapter.mget([key.as_str() for key in keys])

            if t is None:
                return [json.loads(self._b64d(value)) if value is not None else None for value in values]

            return [t.model_validate_json(self._b64d(value)) if value is not None else None for value in values]
        except Exception as e:
            if not silent:
                raise e
            else:
                logger.warning("failed to mget values from cache", keys=[key.as_str() for key in keys], error=str(e))

            return [None] * len(keys)

    @overload
    async def mset(
        self,
        key_values: Mapping[Key, dict[str, Any]],
        *,
        silent: bool = True,
    ) -> None: ...

    @overload
    async def mset(
        self,
        key_values: Mapping[Key, pydantic.BaseModel],
        *,
        silent: bool = True,
    ) -> None: ...

    @span(op="cache_service", name="mset")
    async def mset(
        self,
        key_values: Mapping[Key, pydantic.BaseModel | dict[str, Any]],
        *,
        silent: bool = True,
    ) -> None:
        try:
            data = {
                key.as_str(): self._b64e(
                    value.model_dump_json() if isinstance(value, pydantic.BaseModel) else json.dumps(value)
                )
                for key, value in key_values.items()
            }
            await self._adapter.mset(data)
        except Exception as e:
            if not silent:
                raise e
            else:
                logger.warning(
                    "failed to mset values to cache", keys=[key.as_str() for key in key_values], error=str(e)
                )

    @overload
    async def sadd(
        self,
        key: Key,
        *values: dict[str, Any],
        silent: bool = True,
    ) -> None: ...
    @overload
    async def sadd(
        self,
        key: Key,
        *values: pydantic.BaseModel,
        silent: bool = True,
    ) -> None: ...

    @span(op="cache_service", name="sadd")
    async def sadd(
        self,
        key: Key,
        *values: dict[str, Any] | pydantic.BaseModel,
        silent: bool = True,
    ) -> None:
        try:
            await self._adapter.sadd(
                key.as_str(),
                *[
                    self._b64e(m.model_dump_json()) if isinstance(m, pydantic.BaseModel) else self._b64e(json.dumps(m))
                    for m in values
                ],
            )
        except Exception as e:
            if not silent:
                raise e
            else:
                logger.warning("failed to sadd values to cache", key=key.as_str(), error=str(e))

    @overload
    async def srem(
        self,
        key: Key,
        values: dict[str, Any],
        silent: bool = True,
    ) -> None: ...
    @overload
    async def srem(
        self,
        key: Key,
        values: pydantic.BaseModel,
        silent: bool = True,
    ) -> None: ...

    @span(op="cache_service", name="srem")
    async def srem(
        self,
        key: Key,
        values: dict[str, Any] | pydantic.BaseModel,
        silent: bool = True,
    ) -> None:
        try:
            await self._adapter.srem(
                key.as_str(),
                *[
                    self._b64e(m.model_dump_json()) if isinstance(m, pydantic.BaseModel) else self._b64e(json.dumps(m))
                    for m in values
                ],
            )
        except Exception as e:
            if not silent:
                raise e

    @overload
    async def sismember(
        self,
        key: Key,
        member: dict[str, Any],
        silent: bool = True,
    ) -> bool: ...

    @overload
    async def sismember(
        self,
        key: Key,
        member: pydantic.BaseModel,
        silent: bool = True,
    ) -> bool: ...

    @span(op="cache_service", name="sismember")
    async def sismember(self, key: Key, member: dict[str, Any] | pydantic.BaseModel, silent: bool = True) -> bool:
        try:
            if isinstance(member, pydantic.BaseModel):
                return await self._adapter.sismember(key.as_str(), self._b64e(member.model_dump_json()))

            return await self._adapter.sismember(key.as_str(), self._b64e(json.dumps(member)))
        except Exception as e:
            if not silent:
                raise e
            return False

    @overload
    async def smembers(
        self,
        key: Key,
        t: None = None,
        silent: bool = True,
    ) -> list[dict[str, Any]]: ...
    @overload
    async def smembers(
        self,
        key: Key,
        t: type[T],
        silent: bool = True,
    ) -> list[T]: ...

    @span(op="cache_service", name="smembers")
    async def smembers(
        self,
        key: Key,
        t: type[T] | None = None,
        silent: bool = True,
    ) -> list[dict[str, Any]] | list[T]:
        try:
            members = await self._adapter.smembers(key.as_str())
            if t is not None:
                return [t.model_validate(self._b64d(member)) for member in members]

            return [json.loads(self._b64d(member)) for member in members]
        except Exception as e:
            if not silent:
                raise e
            else:
                logger.warning("failed to smembers values from cache", key=key.as_str(), error=str(e))

            return []

    def _b64e(self, value: str) -> str:
        return base64.b64encode(value.encode("utf-8")).decode("utf-8")

    def _b64d(self, value: str) -> str:
        return base64.b64decode(value).decode("utf-8")
