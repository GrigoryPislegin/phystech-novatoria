from datetime import UTC, datetime
from typing import override

from pydantic import RedisDsn
from redis import asyncio as aioredis

from nanimai_platform.protocols.internal.timed_queue import Oauth2TokenQueueError, Oauth2TokenQueueProtocol
from nanimai_platform.utils import to_utc_timestamp


class RedisOauth2TokenQueueAdapter(Oauth2TokenQueueProtocol):
    _client: aioredis.Redis

    def __init__(self, dsn: RedisDsn):
        self._client = aioredis.from_url(str(dsn))

    @override
    async def upsert_token(self, request: Oauth2TokenQueueProtocol.UpsertTokenRequest) -> None:
        try:
            exp_at = to_utc_timestamp(request.expires_at)
            await self._client.zadd(request.zset_key, {request.token_id: exp_at})
        except Exception as e:
            raise Oauth2TokenQueueError("failed to upsert token") from e

    @override
    async def remove_token(self, request: Oauth2TokenQueueProtocol.RemoveTokenRequest) -> None:
        try:
            await self._client.zrem(request.zset_key, request.token_id)
        except Exception as e:
            raise Oauth2TokenQueueError("failed to remove token") from e

    @override
    async def read_earliest_token(
        self, request: Oauth2TokenQueueProtocol.ReadEarliestTokenRequest
    ) -> Oauth2TokenQueueProtocol.ReadEarliestTokenResponse | None:
        try:
            res = await self._client.zrange(request.zset_key, 0, 0, withscores=True)
            if not res:
                return None
            token_id, score = res[0]
            return Oauth2TokenQueueProtocol.ReadEarliestTokenResponse(
                token_id=token_id,
                expires_at=datetime.fromtimestamp(score, tz=UTC),
            )
        except Exception as e:
            raise Oauth2TokenQueueError("failed to read earliest token") from e
