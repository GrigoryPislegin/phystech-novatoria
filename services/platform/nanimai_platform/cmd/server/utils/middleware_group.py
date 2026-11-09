from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Protocol, final, override

import structlog
from fastapi import FastAPI
from starlette.types import Receive, Scope, Send


class MiddlewareProcotol(Protocol):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None: ...


@final
class MiddlewareGroup(AbstractContextManager["MiddlewareGroup", bool]):
    def __init__(self, app: FastAPI):
        self._app = app
        self._middlewares: list[tuple[type[MiddlewareProcotol], dict[str, Any]]] = []  # pyright: ignore[reportExplicitAny]

    def then(self, mw: type[MiddlewareProcotol], **kwargs: Any) -> MiddlewareGroup:  # pyright: ignore[reportAny,reportExplicitAny]
        self._middlewares.insert(0, (mw, kwargs))  # prepend
        return self

    @override
    def __enter__(self) -> MiddlewareGroup:
        _ = super().__enter__()
        self._middlewares = []
        return self

    @override
    def __exit__(self, *args: Any | None):  # pyright: ignore[reportExplicitAny]
        if any(v is not None for v in args):
            return False  # propagate error value

        log = structlog.stdlib.get_logger("app.general")

        log.info("unrolling middlewares stack")
        for middleware, kwargs in self._middlewares:
            self._app.add_middleware(middleware, **kwargs)  # type: ignore
            log.info("middleware included", middleware=middleware.__name__, args=kwargs)

        return True
