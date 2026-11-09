import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

import structlog

__background_tasks: set[asyncio.Task[Any]] = set()  # pyright: ignore[reportExplicitAny]

log = structlog.stdlib.get_logger("background_tasks")


def __callback(t: asyncio.Task[Any]):  # pyright: ignore[reportExplicitAny]
    if (e := t.exception()) is not None:
        log.error("background task failed", err=e)

    if t.cancelled():
        log.warning("background task was cancelled due to timeout")

    __background_tasks.discard(t)


def launch_background(func: Callable[[], Coroutine[Any, Any, Any]]) -> Callable[[], None]:  # pyright: ignore[reportExplicitAny]
    def launch():
        """launch a function in the background using asyncio.create_task"""
        coro = asyncio.wait_for(func(), timeout=300)
        task = asyncio.create_task(coro)
        __background_tasks.add(task)

        task.add_done_callback(__callback)

    return launch
