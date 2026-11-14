"""Privacy boundary and safe dependency diagnostics for the local application."""
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager



def protect_dependency_logs():
    """Redact dependency diagnostics before handlers/formatters see their contents.

    Process-wide for this CLI/service: even late-created child loggers and exception
    tracebacks must not expose payloads, response bodies or database credentials.
    Application progress uses explicit safe events instead of dependency messages.
    """
    previous = logging.getLogRecordFactory()
    if getattr(previous, '_prototype_private', False):
        return
    namespaces = ('openai', 'httpx', 'httpcore', 'httpx2', 'httpcore2', 'certum_core',
                  'presidio-analyzer', 'presidio_analyzer', 'sqlalchemy', 'asyncpg', 'psycopg',
                  'pdfminer', 'pdfplumber', 'docx', 'PIL', 'pypdfium2')

    def factory(name, level, pathname, lineno, msg, args, exc_info, func=None, sinfo=None, **kwargs):
        if any(name == prefix or name.startswith(prefix + '.') for prefix in namespaces):
            msg, args, exc_info, sinfo = '[dependency diagnostic suppressed]', (), None, None
        return previous(name, level, pathname, lineno, msg, args, exc_info, func, sinfo, **kwargs)

    factory._prototype_private = True
    logging.setLogRecordFactory(factory)


async def check_data(privacy, value):
    """Check decoded JSON strings, including keys; escaping is transport syntax.

    Separate fields by actual newlines, avoiding artificial concatenated reference
    tokens while retaining the source context for the core's detectors.
    """
    def strings(item):
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            for key, child in item.items():
                yield from strings(key)
                yield from strings(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                yield from strings(child)
        elif item is not None:
            yield str(item)
    await privacy.check('\n\n'.join(strings(value)))



@asynccontextmanager
async def local_privacy():
    protect_dependency_logs()
    from .privacy_core import Detector, LocalPrivacy
    from .privacy_core.models import load
    directory = Path(os.environ.get('PRIVACY_MODELS_DIR', 'data/private/privacy-models'))
    privacy = LocalPrivacy(Detector(load(directory)))
    try:
        yield privacy
    finally:
        privacy.close()
