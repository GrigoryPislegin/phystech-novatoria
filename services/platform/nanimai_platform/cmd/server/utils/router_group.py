from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol, final, override, runtime_checkable

import structlog
from fastapi import APIRouter, FastAPI


@dataclass
class RouterConfig:
    path: str
    router: APIRouter
    kwargs: dict[str, Any]  # pyright: ignore[reportExplicitAny]


@runtime_checkable
class RouteInfo(Protocol):
    path: str
    name: str
    methods: list[str]


@final
class RouterGroup(AbstractContextManager["RouterGroup", bool]):
    def __init__(self, app: FastAPI):
        self._app = app
        self._route_builders: list[RouteNodeBuilder] = []

    def at(self, path: str) -> RouteNodeBuilder:
        """Initialize builder object at specify path and register it in internal registry.

        Args:
            path (str): a url path to handle as root for the router

        Returns:
            RouteNodeBuilder: route builder object
        """
        builder = RouteNodeBuilder(self, path)
        self._route_builders.append(builder)
        return builder

    @override
    def __enter__(self) -> RouterGroup:
        _ = super().__enter__()
        self._route_builders = []  # new map
        return self

    @override
    def __exit__(self, *args: Any | None):  # pyright: ignore[reportExplicitAny]
        if any(v is not None for v in args):
            return False  # propagate error value

        log = structlog.stdlib.get_logger("app.general")
        for builder in self._route_builders:
            config = builder.build()
            self._app.include_router(prefix=config.path, router=config.router, **config.kwargs)  # pyright: ignore[reportAny]
            log.info("registered router", path=config.path or "/")

            for route in config.router.routes:
                if isinstance(route, RouteInfo):
                    for method in route.methods:
                        log.debug("registered route", path=config.path + route.path, name=route.name, method=method)

        return True


@final
class RouteNodeBuilder:
    def __init__(self, parent: RouterGroup, path: str):
        self._parent = parent
        self._path = path

        self._router: APIRouter | None = None
        self._router_kwargs: dict[str, Any] = {}  # pyright: ignore[reportExplicitAny]

    def build(self) -> RouterConfig:
        if self._router is None:
            raise ValueError("partially configured routers are not available")

        return RouterConfig(self._path, self._router, self._router_kwargs)

    def handle(self, router: APIRouter) -> RouteNodeBuilder:
        """Specify router to handle request at this path

        Args:
            router (APIRouter): handler to handle http requests

        Returns:
            RouteNodeBuilder: the same object
        """
        self._router = router
        return self

    def with_args(self, **kwargs: Any) -> RouteNodeBuilder:  # pyright: ignore[reportExplicitAny,reportAny]
        """
        Refer to :func:`FastAPI's include_router <fastapi.FastAPI.include_router>` to find possible keyword arguments
        """
        self._router_kwargs.update(kwargs)
        return self
