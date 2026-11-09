import json
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


def pymongo_unwrap(_, __: str, event_dict: EventDict) -> EventDict:  # pyright: ignore[reportUnusedParameter]
    if not event_dict.get("logger", "").startswith("pymongo"):
        return event_dict

    try:
        data: EventDict = json.loads(event_dict.get("event", "{}"))
        event_dict.update(data)
        event_dict["event"] = data.get("message", "")

        return event_dict
    except Exception:
        return event_dict


def err_to_exc_info(_, __: str, event_dict: EventDict) -> EventDict:  # pyright: ignore[reportUnusedParameter]
    if "exc_info" in event_dict:
        return event_dict

    if "err" in event_dict:
        event_dict["exc_info"] = event_dict.pop("err", None)

    return event_dict


def add_span_as_event(_, __: str, event_dict: EventDict) -> EventDict:  # pyright: ignore[reportUnusedParameter]
    event_dict["message"] = event_dict.get("event", None)
    event_dict["event"] = event_dict.get("span", None)

    if "span" in event_dict:
        del event_dict["span"]

    return event_dict


def configure_logger(json_mode: bool = False, log_level: str = "INFO"):
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
        # pymongo_unwrap,
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
        processors=shared_processors
        + [
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

    logging.getLogger("uvicorn").handlers.clear()
    logging.getLogger("uvicorn").propagate = True

    logging.getLogger("uvicorn.error").handlers.clear()
    logging.getLogger("uvicorn.error").propagate = True

    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").propagate = True

    logging.getLogger("pymongo.command").handlers.clear()
    logging.getLogger("pymongo.command").setLevel(logging.WARNING)
    logging.getLogger("pymongo.command").propagate = True

    logging.getLogger("pymongo.connection").handlers.clear()
    logging.getLogger("pymongo.connection").setLevel(logging.WARNING)
    logging.getLogger("pymongo.connection").propagate = False

    logging.getLogger("pymongo.topology").handlers.clear()
    logging.getLogger("pymongo.topology").setLevel(logging.WARNING)
    logging.getLogger("pymongo.topology").propagate = False

    logging.getLogger("pymongo.serverSelection").handlers.clear()
    logging.getLogger("pymongo.serverSelection").setLevel(logging.WARNING)
    logging.getLogger("pymongo.serverSelection").propagate = False

    logging.getLogger("aiormq.connection").handlers.clear()
    logging.getLogger("aiormq.connection").setLevel(logging.WARNING)
    logging.getLogger("aiormq.connection").propagate = False

    logging.getLogger("aio_pika.connection").disabled = True
    logging.getLogger("aio_pika.exchange").disabled = True
    logging.getLogger("aio_pika.channel").disabled = True
    logging.getLogger("aio_pika.queue").disabled = True
    logging.getLogger("aio_pika.robust_connection").disabled = True

    logging.getLogger("urllib3.connectionpool").handlers.clear()
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
    logging.getLogger("urllib3.connectionpool").propagate = False

    logging.getLogger("hpack.hpack").disabled = True
    logging.getLogger("httpcore.http11").disabled = True

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
