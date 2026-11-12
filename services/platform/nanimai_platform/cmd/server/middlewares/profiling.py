from collections.abc import Callable
from typing import override
from uuid import uuid4

from fastapi import Request
from pyinstrument import Profiler
from pyinstrument.renderers.speedscope import SpeedscopeRenderer
from starlette.middleware.base import BaseHTTPMiddleware


class ProfileRequestMiddleware(BaseHTTPMiddleware):
    @override
    async def dispatch(self, request: Request, call_next: Callable):
        if request.query_params.get("profile", False):
            with Profiler(interval=0.0001, async_mode="strict", use_timing_thread=True) as profiler:
                response = await call_next(request)

            renderer = SpeedscopeRenderer()
            with open(
                (
                    f"profile-{request.method}-"
                    f"{request.url.path.removesuffix('/').replace('/', '-')}-"
                    f"{response.headers.get('x-request-id', uuid4())}.json"
                ),
                "w",
            ) as out:
                out.write(profiler.output(renderer=renderer))
            return response

        return await call_next(request)
