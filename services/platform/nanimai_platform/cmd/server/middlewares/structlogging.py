import time
from collections.abc import Awaitable, Callable
from typing import override

import structlog
from asgi_correlation_id.context import correlation_id
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from uvicorn.protocols.utils import get_path_with_query_string


class StructLoggingMiddleware(BaseHTTPMiddleware):
    @override
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = correlation_id.get()
        _ = structlog.contextvars.bind_contextvars(request_id=request_id)

        request_start_time = time.perf_counter_ns()
        response = Response(status_code=500, content="Internal Server Error")  # default response
        try:
            response = await call_next(request)
        except Exception as e:
            structlog.stdlib.get_logger("api.error").exception("uncaught exception", err=e)
            raise
        finally:
            process_time = time.perf_counter_ns() - request_start_time

            url = get_path_with_query_string(request.scope)  # type: ignore
            client_host = client.host if (client := request.client) is not None else ""
            client_port = client.port if (client := request.client) is not None else ""

            if all(
                path not in url
                for path in [
                    "/api/v1/auth/sign-in",
                    "/api/v1/auth/sign-up",
                    "/api/v1/auth/token-refresh",
                    "/api/v1/auth/logout",
                    "/api/v1/healthz",
                ]
            ):
                structlog.stdlib.get_logger("api.access").info(
                    f"""{client_host}:{client_port} - {request.method} {url} {response.status_code}""",
                    url=str(request.url),
                    status_code=response.status_code,
                    method=request.method,
                    request_id=request_id,
                    client_host=client_host,
                    client_port=client_port,
                    duration=process_time,
                    x_forwarded_for=request.headers.get("x-forwarded-for"),
                    user_agent=request.headers.get("user-agent"),
                )

            response.headers["x-process-time"] = str(process_time / 10**9)
            return response  # noqa: B012
