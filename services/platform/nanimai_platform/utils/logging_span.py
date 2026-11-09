import inspect
from contextlib import contextmanager
from functools import wraps

import structlog

log = structlog.stdlib.get_logger("app.span")


def span(op: str, name: str):
    def decorator(func):
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                with _add_span_context(f"{op}.{name}"):
                    return await func(*args, **kwargs)

            return async_wrapper

        @wraps(func)
        def wrapper(*args, **kwargs):
            with _add_span_context(f"{op}.{name}"):
                return func(*args, **kwargs)

        return wrapper

    return decorator


@contextmanager
def _add_span_context(span_name: str):
    original_span: str | None = structlog.contextvars.get_contextvars().get("span", None)
    _ = structlog.contextvars.bind_contextvars(span=span_name)
    # start_time = time.perf_counter()
    try:
        yield
    finally:
        # elapsed_ms = (time.perf_counter() - start_time) * 1000
        # log.trace("span_completed", span=span_name, duration_ms=round(elapsed_ms, 2))
        if original_span is None:
            structlog.contextvars.unbind_contextvars("span")
        else:
            _ = structlog.contextvars.bind_contextvars(span=original_span)
