"""Privacy boundary and safe dependency diagnostics for the local application."""
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from .errors import PrivacyError



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


async def check_data(privacy, value, *, prepared=False, stage='privacy', direction='outbound'):
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
    try:
        if prepared and hasattr(privacy, 'check_prepared_fields'):
            await privacy.check_prepared_fields(list(strings(value)))
        else:
            check = privacy.check_prepared if prepared and hasattr(privacy, 'check_prepared') else privacy.check
            await check('\n\n'.join(strings(value)))
    except RuntimeError as exc:
        known = {'privacy_residual_findings','privacy_untrusted_reference','privacy_detector_failed','privacy_closed',
                 'privacy_scan_limit'}
        if isinstance(exc, PrivacyError) or (type(exc) is RuntimeError and str(exc) in known):
            error = exc if isinstance(exc, PrivacyError) else PrivacyError(str(exc))
            error.diagnostic['stage'] = stage if stage in {'facts','requirements','evaluation','privacy'} else 'privacy'
            error.diagnostic['direction'] = direction if direction in {'outbound','response'} else 'outbound'
            raise error from None
        raise



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
