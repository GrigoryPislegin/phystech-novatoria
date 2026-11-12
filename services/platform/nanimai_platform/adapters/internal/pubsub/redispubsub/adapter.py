from collections.abc import AsyncGenerator
from typing import override

from pydantic import RedisDsn
from redis import asyncio as aioredis

from nanimai_platform.protocols.internal import pubsub as protocol


class RedisPubSubAdapter(protocol.PubSubProtocol):
    _client: aioredis.Redis

    def __init__(self, dsn: RedisDsn):
        self._client = aioredis.from_url(str(dsn))

    @override
    async def publish(self, room: str, message: str) -> None:
        try:
            await self._client.publish(room, message)
        except Exception as e:
            raise protocol.PubSubError(f"failed to publish message to room: {e}") from e

    @override
    async def subscribe(self, room: str) -> AsyncGenerator[str, None]:
        try:
            pubsub = self._client.pubsub()
            await pubsub.subscribe(room)

            try:
                async for message in pubsub.listen():  # pyright: ignore[reportUnknownVariableType]
                    if message["type"] == "message":
                        data: str | bytes = message["data"]  # pyright: ignore[reportUnknownVariableType]
                        yield data.decode("utf-8") if isinstance(data, bytes) else data
            finally:
                await pubsub.unsubscribe(room)
                await pubsub.close()
        except Exception as e:
            raise protocol.PubSubError(f"failed to subscribe to room: {e}") from e
