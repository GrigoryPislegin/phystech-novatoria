import logging
import sys

import structlog
from structlog.types import EventDict, Processor


def drop_color_message_key(_, __: str, event_dict: EventDict) -> EventDict:  # pyright: ignore[reportUnusedParameter]
    """
    Uvicorn logs the message a second time in the extra `color_message`, but we don't
    need it. This processor drops the key from the event dict if it exists.
    """
    event_dict.pop("color_message", None)
    return event_dict


def err_to_exc_info(_, __: str, event_dict: EventDict) -> EventDict:  # pyright: ignore[reportUnusedParameter]
    """Convert 'err' key to 'exc_info' for proper exception logging."""
    if "exc_info" in event_dict:
        return event_dict

    if "err" in event_dict:
        event_dict["exc_info"] = event_dict.pop("err", None)

    return event_dict


def add_span_as_event(_, __: str, event_dict: EventDict) -> EventDict:  # pyright: ignore[reportUnusedParameter]
    """Convert span to event for better log structure."""
    event_dict["message"] = event_dict.get("event", None)
    event_dict["event"] = event_dict.get("span", None)

    if "span" in event_dict:
        del event_dict["span"]

    return event_dict


def configure_logger(*, json_mode: bool = False, log_level: str = "INFO") -> None:
    """Configure structlog logger with processors and formatters.

    Args:
        json_mode: If True, output logs in JSON format. Otherwise, use console renderer.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.CallsiteParameterAdder(
            [
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ],
        ),
        structlog.processors.StackInfoRenderer(),
        err_to_exc_info,
        drop_color_message_key,
        add_span_as_event,
    ]

    if json_mode:
        shared_processors.extend([
            structlog.processors.ExceptionRenderer(
                structlog.tracebacks.ExceptionDictTransformer(),
            ),
            structlog.processors.format_exc_info,
        ])

    structlog.configure(
        processors=[
            *shared_processors,
            # Prepare event dict for `ProcessorFormatter`.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(ensure_ascii=False) if json_mode else structlog.dev.ConsoleRenderer(),
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())

    # Configure specific loggers - gRPC and database
    logging.getLogger("grpclib").handlers.clear()
    logging.getLogger("grpclib").setLevel(logging.WARNING)
    logging.getLogger("grpclib").propagate = True

    logging.getLogger("sqlalchemy.engine").handlers.clear()
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").propagate = True

    logging.getLogger("asyncpg").handlers.clear()
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").propagate = True

    # Configure HTTP/network loggers
    logging.getLogger("urllib3.connectionpool").handlers.clear()
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
    logging.getLogger("urllib3.connectionpool").propagate = False

    logging.getLogger("hpack.hpack").disabled = True
    logging.getLogger("httpcore.connection").disabled = True
    logging.getLogger("httpcore.http11").disabled = True
    logging.getLogger("aiormq.connection").disabled = True
    logging.getLogger("aio_pika.connection").disabled = True
    logging.getLogger("aio_pika.exchange").disabled = True
    logging.getLogger("aio_pika.channel").disabled = True
    logging.getLogger("aio_pika.queue").disabled = True
    logging.getLogger("aio_pika.robust_connection").disabled = True

    def handle_exception(exc_type, exc_value, exc_traceback):  # pyright: ignore[reportMissingParameterType,reportUnknownParameterType]
        """
        Log any uncaught exception instead of letting it be printed by Python
        (but leave KeyboardInterrupt untouched to allow users to Ctrl+C to stop)
        """
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)  # pyright: ignore[reportUnknownArgumentType]
            return

        root_logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))  # pyright: ignore[reportUnknownArgumentType]

    sys.excepthook = handle_exception
