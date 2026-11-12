import json
import logging
import sys

import structlog
from structlog.types import EventDict, Processor


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

    event_dict["exc_info"] = event_dict.get("err", None)
    return event_dict


def add_span_as_event(_, __: str, event_dict: EventDict) -> EventDict:  # pyright: ignore[reportUnusedParameter]
    event_dict["message"] = event_dict.get("event", None)
    event_dict["event"] = event_dict.get("span", None)

    if "span" in event_dict:
        del event_dict["span"]

    return event_dict


def configure_logger(json_mode: bool = False, log_level: str = "INFO"):
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.stdlib.add_log_level,
        structlog.processors.CallsiteParameterAdder(
            [
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ],
        ),
        err_to_exc_info,
        # pymongo_unwrap,
        add_span_as_event,
        structlog.processors.StackInfoRenderer(),
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

    logging.getLogger("pymongo.command").handlers.clear()
    logging.getLogger("pymongo.command").setLevel(logging.WARNING)
    logging.getLogger("pymongo.command").propagate = True

    logging.getLogger("pymongo.connection").handlers.clear()
    logging.getLogger("pymongo.connection").setLevel(logging.WARNING)
    logging.getLogger("pymongo.connection").propagate = False

    for name in [
        "PIL.Image",
        "pymongo.connection",
        "pymongo.topology",
        "botocore.hooks",
        "botocore.loaders",
        "aiobotocore.regions",
        "botocore.regions",
        "botocore.endpoint",
        "botocore.auth",
        "botocore.httpsession",
        "botocore.parsers",
        "botocore.retryhandler",
        "botocore.utils",
        "pymongo.serverSelection",
        "aiormq.connection",
        "aio_pika.connection",
        "aio_pika.robust_connection",
        "hpack.hpack",
        "pypandoc",
        "ocrmypdf",
        "pdfminer",
    ]:
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).addHandler(handler)
        logging.getLogger(name).propagate = True
        logging.getLogger(name).setLevel(logging.WARNING)

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
