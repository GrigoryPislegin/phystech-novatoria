"""Shared local application boundary. Transport and scoring live elsewhere."""
import hashlib
import asyncio
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path

from .documents import MAX_JOBS, read_document
from .pipeline import RunControl, preflight_output, run_pipeline, write_report, refresh_derived
from .privacy import protect_dependency_logs


def _input_file(path):
    if path.is_symlink():
        raise ValueError('input_symlink')
    if not path.is_file():
        raise ValueError('input_invalid')
    if path.suffix.lower() not in {'.txt', '.md', '.pdf', '.docx'}:
        raise ValueError('input_unsupported')
    if path.stat().st_size > 5_000_000:
        raise ValueError('input_too_large')


def load_documents(resume_path, jobs_root, *, reader=read_document, control=None):
    """Validate the entire set before opening any document. Names stay local."""
    protect_dependency_logs()
    resume_path, jobs_root = Path(resume_path), Path(jobs_root)
    if jobs_root.is_symlink():
        raise ValueError('input_symlink')
    if not jobs_root.is_dir():
        raise ValueError('input_invalid')
    files = []
    for path in jobs_root.iterdir():
        if path.name.startswith('.'):
            continue
        files.append(path)
        if len(files) > MAX_JOBS:
            raise ValueError('invalid_job_set')
    if not files:
        raise ValueError('invalid_job_set')
    for path in [resume_path, *files]:
        _input_file(path)
    if control:
        control.emit('parsing')
        control.checkpoint()
    resume = reader(resume_path)
    jobs, entries, counts = [], [], {}
    for path in sorted(files):
        if control:
            control.checkpoint()
        text = reader(path)
        digest = hashlib.sha256(text.encode()).hexdigest()
        counts[digest] = counts.get(digest, 0) + 1
        job_id = 'job-' + digest[:24] + '-' + str(counts[digest])
        jobs.append((job_id, text))
        entries.append({'job_id':job_id, 'filename':path.name, 'text_sha256':digest})
    manifest = {'resume':{'filename':resume_path.name, 'text_sha256':hashlib.sha256(resume.encode()).hexdigest()},
                'jobs':entries, 'scope':'local_only_not_model_payload'}
    return resume, jobs, manifest


@dataclass
class RunResult:
    report: dict
    path: Path | None
    display_aliases: dict[str, str] = field(default_factory=dict, repr=False, compare=False)

    @property
    def exit_code(self):
        return 0 if self.report['ranking']['complete'] else 2


async def analyze(resume, jobs, *, model_factory, privacy, out, mode, control=None, manifest=None, metadata=None,
                  _defer_publication=False, source_sink=None):
    """Run once and atomically publish. The caller explicitly selects data/mode.

    No run retries, task queue, network listener or implicit live fallback. The
    live model may retry an invalid output once within the same budget. A web
    transport must enforce its own upload/session boundary before calling here.
    """
    control = control or RunControl()
    control.emit('validating_inputs')
    control.checkpoint()
    if metadata and (set(metadata) != {'demo_scenario'} or metadata['demo_scenario'] not in {'success', 'disputed'}):
        raise ValueError('invalid_metadata')
    if not jobs or len(jobs) > MAX_JOBS or len({jid for jid, _ in jobs}) != len(jobs):
        raise ValueError('invalid_job_set')
    if any(not isinstance(text, str) or not text.strip() or len(text) > 60_000 for text in [resume, *(text for _,text in jobs)]):
        raise ValueError('input_invalid')
    preflight_output(out)
    model = model_factory()
    try:
        report = await run_pipeline(resume, jobs, model, privacy, control=control, source_sink=source_sink)
        report.update(metadata or {})
        report['mode'] = mode
        if hasattr(privacy, 'summary'):
            report['privacy'] = privacy.summary()
        refresh_derived(report)
        report['model'] = getattr(model, 'model', None)
        if getattr(model, 'response_normalizations', None):
            report['model_response_normalizations'] = list(model.response_normalizations)
        if getattr(model, 'response_retries', None):
            report['model_response_retries'] = list(model.response_retries)
        if hasattr(model, 'budget'):
            report['usage'] = model.usage
            report['reserved_usd_estimate'] = str(model.budget.reserved)
            rates = model.budget.rates
            from decimal import Decimal
            estimate = str(sum((Decimal(u['input_tokens'])*rates[0] + Decimal(u['output_tokens'])*rates[1])/1_000_000 for u in model.usage))
            report['usage_complete'] = getattr(model, 'usage_complete', True)
            report['usage_usd_estimate'] = estimate if report['usage_complete'] else None
            report['recorded_usage_usd_estimate'] = estimate
            report['budget_remaining_reservation_usd'] = str(model.budget.limit - model.budget.reserved)
            report['provider_balance'] = 'unknown'
        # A deadline/cancel must not discard successfully computed partial results.
        path = None
        if not _defer_publication:
            control.emit('export')
            path = write_report(report, out, manifest=manifest)
        return RunResult(report, path)
    finally:
        if hasattr(model, 'close'):
            await model.close()


async def analyze_protected(resume, jobs, *, privacy_context, model_factory, out, control=None, manifest=None,
                            source_sink=None, mode='live_local_privacy'):
    """Close the privacy session before publishing references in a report.

    Async startup observes the processing deadline; close/commit gets a separate
    30-second cleanup window so a cancelled partial run may still be saved.
    """
    control = control or RunControl()
    preflight_output(out)
    stack = AsyncExitStack()
    try:
        privacy = await control.call(lambda: stack.enter_async_context(privacy_context()), 'privacy_startup')
        result = await analyze(resume, jobs, model_factory=lambda:model_factory(privacy),
            privacy=privacy, out=out, mode=mode, control=control, manifest=manifest,
            _defer_publication=True, source_sink=source_sink)
        if hasattr(privacy, 'export_display_aliases'):
            result.display_aliases = privacy.export_display_aliases()
    except BaseException:
        await asyncio.wait_for(stack.__aexit__(*sys.exc_info()), timeout=30)
        raise
    else:
        await asyncio.wait_for(stack.__aexit__(None, None, None), timeout=30)
    control.emit('export')
    result.path = write_report(result.report, out, manifest=manifest)
    return result
