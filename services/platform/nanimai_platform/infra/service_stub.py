from collections.abc import AsyncGenerator

from grpclib.client import Channel

from nanimai_platform.external_clients.hharon.hharon_api.v1 import HharonServiceStub
from nanimai_platform.infra.config import PlatformConfig


async def provide_hharon_service_stub(cfg: PlatformConfig) -> AsyncGenerator[HharonServiceStub]:
    channel = Channel(cfg.hharon_grpc.host, cfg.hharon_grpc.port)
    try:
        yield HharonServiceStub(channel)
    finally:
        channel.close()
