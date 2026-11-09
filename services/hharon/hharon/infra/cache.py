from collections.abc import AsyncGenerator
from datetime import timedelta

from glide import GlideClient, GlideClientConfiguration, NodeAddress
from pydantic import BaseModel, Field


class CacheConfig(BaseModel):
    """Configuration for Valkey/Redis cache."""

    host: str = Field(default="localhost", description="Valkey host")
    port: int = Field(default=6379, description="Valkey port")
    use_tls: bool = Field(default=False, description="Use TLS for connection")
    cache_ttl: timedelta = Field(
        default=timedelta(minutes=10), description="Cache TTL in seconds (default: 10 minutes)"
    )


async def provide_glide_client(config: CacheConfig) -> AsyncGenerator[GlideClient]:
    """Provider for GlideClient with lifecycle management."""
    client = await GlideClient.create(
        GlideClientConfiguration(
            addresses=[NodeAddress(config.host, config.port)],
            use_tls=config.use_tls,
            request_timeout=5000,
        )
    )
    try:
        yield client
    finally:
        await client.close()
