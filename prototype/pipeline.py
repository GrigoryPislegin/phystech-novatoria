import csv
import asyncio
import hashlib
import json
import os
import re
import math
import shutil
import tempfile
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from .contracts import Facts, Requirements, RequirementFactors, Evaluation, validate_pair
from .scoring import score, rank, POLICY_VERSION
from .analysis_contracts import ResumeAnalysis, RequirementsAnalysis, VacancyAnalysis
from .candidate_profile import check_profile, check_conditions
from .ranking_explanation import compare, explain_leader, competency_axes
from .review_queue import build_review_queue
from .review_policy import assess_handoff
from .evidence import Source, check_pair
from . import requirements_review as review
from .errors import ModelOutputError, RunStopped, PrivacyError, error_code
from .documents import MAX_JOBS
from .presentation import build_presentation, display_label, gap_question, EXPLANATIONS


class RunControl:
    """One run's deadline, cancellation and text-free stage events."""
    def __init__(self, timeout_seconds=300, progress=None, *, defer_start=False):
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0 or timeout_seconds > 1800:
            raise ValueError('invalid_deadline')
        self.timeout_seconds = timeout_seconds
        self.started, self.deadline = None, math.inf
        self.progress = progress
        self.cancelled = False
        self._cancelled_at = None
        self.events = []
        self._pending = set()
        self._pending_lock = threading.Lock()
        if not defer_start:
            self.start()

    def start(self):
        """Start the execution clock once; queued time must not consume it."""
        if self.started is None:
            self.started = time.monotonic()
            self.deadline = self.started + self.timeout_seconds

    def cancel(self):
        # The HTTP transport calls this from a different thread than the
        # analysis event loop. Wake pending I/O through its owning loop.
        with self._pending_lock:
            if self.cancelled:
                return
            self.cancelled = True
            self._cancelled_at = time.monotonic()
            pending = list(self._pending)
        for signal in pending:
            try:
                signal.get_loop().call_soon_threadsafe(self._signal_cancel, signal)
            except RuntimeError:
                pass  # The owning loop already finished and closed.

    @staticmethod
    def _signal_cancel(signal):
        if not signal.done():
            signal.set_result(None)

    def checkpoint(self):
        self.start()
        if self._cancelled_at is not None and self._cancelled_at <= self.deadline:
            raise RunStopped('cancelled')
        if time.monotonic() >= self.deadline:
            raise RunStopped('deadline_exceeded')

    @staticmethod
    async def _drain(task):
        """Finish cancellation cleanup even if the caller is cancelled again."""
        waiter = asyncio.gather(task, return_exceptions=True)
        interrupted = False
        while not waiter.done():
            try:
                await asyncio.shield(waiter)
            except asyncio.CancelledError:
                interrupted = True
        return interrupted

    def emit(self, stage, job_id=None):
        self.start()
        event = {'stage':stage, 'job_id':job_id, 'elapsed_ms':round((time.monotonic()-self.started)*1000)}
        self.events.append(event)
        if self.progress:
            self.progress(dict(event))

    async def call(self, operation, stage, job_id=None):
        self.emit(stage, job_id)
        self.checkpoint()
        task = asyncio.create_task(operation())
        signal = asyncio.get_running_loop().create_future()
        cancelling = False
        with self._pending_lock:
            self._pending.add(signal)
            if self.cancelled:
                signal.set_result(None)
                task.cancel()
                cancelling = True
        try:
            caller_cancelled = False
            try:
                done, _ = await asyncio.wait((task, signal),
                    timeout=max(0, self.deadline-time.monotonic()), return_when=asyncio.FIRST_COMPLETED)
            except asyncio.CancelledError:
                caller_cancelled = True
                done = set()
            with self._pending_lock:
                cancelled_at = self._cancelled_at
            reason = ('cancelled' if cancelled_at is not None and cancelled_at <= self.deadline
                      else 'deadline_exceeded' if task not in done else None)
            if reason or caller_cancelled:
                # Once a reason wins, there is no second deadline timer to
                # interrupt the operation's asynchronous cancellation cleanup.
                if not cancelling:
                    task.cancel()
                    cancelling = True
                caller_cancelled |= await self._drain(task)
                if caller_cancelled:
                    raise asyncio.CancelledError
                raise RunStopped(reason)
            result = task.result()
        finally:
            with self._pending_lock:
                self._pending.discard(signal)
            signal.cancel()
        self.checkpoint()
        return result


def literal(value):
    """CommonMark code span: source text cannot become a link, image or raw HTML."""
    text = str(value).replace('\n', ' ').replace('\r', ' ')
    fence = '`' * (max((len(x) for x in re.findall(r'`+', text)), default=0) + 1)
    return f'{fence} {text} {fence}'


def failure(exc, stage, job_id=None):
    result = {'job_id':job_id, 'code':error_code(exc, stage), 'stage':stage, 'type':type(exc).__name__}
    if isinstance(exc, PrivacyError):
        result['privacy'] = exc.diagnostic
    return result


def refresh_derived(report, decisions=()):
    """Deterministic presentation only; no model calls, no changes to model statuses."""
    ranked = report['ranking']['jobs']
    report['comparisons'] = [compare(report, ranked[0]['job_id'], job['job_id']).model_dump()
                             for job in ranked[1:]]
    leader = explain_leader(report)
    report['leader'] = leader.model_dump() if leader is not None else None
    report['review_queue'] = build_review_queue(report).model_dump()
    report['handoff'] = [assess_handoff(report, list(decisions), job['job_id']).model_dump()
                         for job in ranked]
    report['presentation'] = build_presentation(report)
    for job in ranked:
        labels = job.get('requirement_factors')
        factors = RequirementFactors.model_validate(labels) if labels is not None else None
        if factors is not None:
            factors.validate_requirements(Requirements.model_validate(job['requirements']))
        grouped = {item.requirement_id:item.factor for item in factors.items} if factors is not None else None
        if grouped is not None:
            # A scoring unit may merge normalized duplicate requirements. No
            # first-ID choice: contradictory or incomplete labels leave the
            # entire unit outside the chart while its score stays unchanged.
            for unit in job['score'].get('units', []):
                if len({grouped.get(rid) for rid in unit['ids']}) != 1:
                    for rid in unit['ids']:
                        grouped.pop(rid, None)
        # Legacy v3 scores have no additive shares/breakdown. Keep them readable
        # without silently changing their saved calculation or inventing labels.
        axes = (competency_axes(job, grouped)
                if 'shares' in job['score'] and 'breakdown' in job['score'] else None)
        job['competency_axes'] = axes.model_dump() if axes is not None else None
    return report


async def run_pipeline(resume, jobs, model, privacy, *, control=None, source_sink=None):
    if not jobs or len(jobs) > MAX_JOBS or len({j[0] for j in jobs}) != len(jobs):
        raise ValueError('invalid_job_set')
    control = control or RunControl(timeout_seconds=300 if len(jobs) <= 3 else 1800)
    if hasattr(model, 'set_run_control'):
        model.set_run_control(control)
    safe_resume = await control.call(lambda: privacy.redact(resume), 'privacy')
    # Complete privacy preflight before the very first model call.
    safe_jobs = [(jid, await control.call(lambda: privacy.redact(text), 'privacy', jid)) for jid, text in jobs]
    if hasattr(privacy, 'finalize_sources'):
        sources = await control.call(lambda:privacy.finalize_sources([safe_resume, *(text for _,text in safe_jobs)]), 'privacy')
        safe_resume = sources[0]
        safe_jobs = [(jid, text) for (jid, _), text in zip(safe_jobs, sources[1:], strict=True)]
    if source_sink is not None:
        source_sink({'resume':safe_resume, 'jobs':dict(safe_jobs)})
    cv_source = Source.of('cv', safe_resume)
    results, errors, review_checks = [], [], {}
    profile_check = None
    profile_missing = ['summary', 'stack', 'last_position', 'achievements']
    def finish(facts):
        order = {jid:index for index,(jid,_) in enumerate(jobs)}
        results.sort(key=lambda result:order[result['job_id']])
        errors.sort(key=lambda error:order.get(error['job_id'], -1))
        missing = [jid for jid,_ in jobs if jid not in {r['job_id'] for r in results}]
        by_job = {e['job_id']:e['code'] for e in errors}
        control.emit('analysis_finished')
        report = {'schema_version':'0.1', 'facts':facts.model_dump(), 'ranking':rank(results, len(jobs)),
                'errors':errors, 'unprocessed_job_ids':missing,
                'unprocessed':[{'job_id':jid, 'reason':by_job.get(jid, by_job.get(None, 'stopped_after_error'))} for jid in missing],
                'events':control.events,
                'safe_resume_sha256':hashlib.sha256(safe_resume.encode()).hexdigest()}
        report['analysis_schema_version'] = 'analysis-0.2'
        report['policy_version'] = POLICY_VERSION
        report['profile'] = profile_check.model_dump() if profile_check is not None else None
        report['profile_missing'] = profile_missing
        report['requirements_review'] = review.summarize(report['ranking']['complete'], review_checks,
            expected_ids=[jid for jid, _ in jobs]).model_dump()
        report['verification'] = {'requirements':'not_reviewed',
                                  'evidence':'quotes_checked_semantics_unverified',
                                  'final_allowed':False}
        return refresh_derived(report)
    stage = 'facts'
    try:
        extracted = await control.call(lambda: model.ask(ResumeAnalysis, 'facts', {'text':safe_resume}), stage)
        stage = 'facts_validation'
        extracted = ResumeAnalysis.model_validate(extracted.model_dump())
        facts = Facts(items=extracted.items)
        facts.validate_source(safe_resume)
        # An invalid profile is shown as «не удалось проверить» and queued (profile_review);
        # it must not cost the ranking of every vacancy.
        profile_check = check_profile(extracted.profile, facts, cv_source)
        profile_missing = extracted.profile.missing
    except Exception as exc:
        errors.append(failure(exc, stage))
        return finish(Facts(items=[]))
    async def analyze_job(jid, text):
        stage = 'requirements'
        try:
            extracted_requirements = await control.call(
                lambda: model.ask(RequirementsAnalysis, 'requirements', {'text':text}), stage, jid)
            stage = 'requirements_validation'
            contract_warnings = list(getattr(extracted_requirements, '_contract_warnings', []))
            extracted_requirements = RequirementsAnalysis.model_validate(extracted_requirements.model_dump())
            extracted_requirements.validate_source(text)
            requirements = Requirements(items=extracted_requirements.items)
            stage = 'evaluation'
            assessed = await control.call(lambda: model.ask(VacancyAnalysis, 'evaluation', {
                'requirements':requirements.model_dump(), 'facts':facts.model_dump(),
                'vacancy_text':text}), stage, jid)
            stage = 'evaluation_validation'
            assessed = VacancyAnalysis.model_validate(assessed.model_dump())
            evaluation = Evaluation(rows=assessed.rows)
            validate_pair(requirements, facts, evaluation)
            job_source = Source.of(jid, text)
            # Invalid conditions block this vacancy's handoff (queue: invalid_evidence) but keep it ranked.
            conditions = check_conditions(assessed.conditions, facts, cv_source, job_source)
            evidence = check_pair(requirements, facts, evaluation, cv_source, job_source)
            if evidence.has_invalid:
                raise ModelOutputError('invalid_evidence')
            review_checks[jid] = review.check(None, jid, text, requirements)
            computed_score = score(requirements, evaluation, evidence)
            results.append({'job_id':jid, 'requirements':requirements.model_dump(),
                            'contract_warnings':contract_warnings,
                            'requirement_factors':(extracted_requirements.factors.model_dump()
                                                   if extracted_requirements.factors is not None else None),
                            'evidence_check':evidence.model_dump(),
                            'requirements_draft':review.draft(jid, text, requirements).model_dump(),
                            'requirements_review':review_checks[jid].model_dump(),
                            'evaluation':evaluation.model_dump(), 'score':computed_score,
                            'conditions':conditions.model_dump(),
                            'score_review':{'excluded_mandatory_ids':computed_score['excluded_mandatory_ids'],
                                'rule':'evidence_applied_by_scoring_policy', 'version':POLICY_VERSION},
                            'safe_source_sha256':hashlib.sha256(text.encode()).hexdigest()})
            control.emit('job_finished', jid)
            return False
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise  # Caller/peer cancellation must finish via the pool drain.
            # A transport that cancels its own task is a terminal operation
            # failure, not permission to silently skip this vacancy.
            errors.append(failure(RuntimeError('operation_cancelled'), stage, jid))
            return True
        except Exception as exc:
            # Never serialize exception messages: upstream errors may contain text/keys/DSNs.
            code = error_code(exc, stage)
            errors.append(failure(exc, stage, jid))
            # Only known output-validation failures are recoverable, without retry.
            return code != 'model_invalid'

    if len(safe_jobs) <= 3:
        for jid, text in safe_jobs:
            if await analyze_job(jid, text):
                break
    else:
        # Only the per-vacancy phase overlaps. All sources are finalized and
        # facts extracted first; workers share one model and its atomic budget.
        # At most three requests are in flight, with no hidden background work
        # after cancellation, a terminal failure or the returned report.
        remaining, workers, stopped = iter(safe_jobs), [], False

        async def worker():
            nonlocal stopped
            while not stopped:
                job = next(remaining, None)
                if job is None:
                    return
                if await analyze_job(*job):
                    stopped = True
                    current = asyncio.current_task()
                    for task in workers:
                        if task is not current and not task.done():
                            task.cancel()
                    return

        workers = [asyncio.create_task(worker()) for _ in range(3)]
        try:
            outcomes = await asyncio.gather(*workers, return_exceptions=True)
            for outcome in outcomes:
                if isinstance(outcome, BaseException) and not (stopped and isinstance(outcome, asyncio.CancelledError)):
                    raise outcome
        finally:
            for task in workers:
                if not task.done():
                    task.cancel()
            await control._drain(asyncio.gather(*workers, return_exceptions=True))
    return finish(facts)


def preflight_output(root: Path):
    try:
        root = Path(root)
        if root.is_symlink():
            raise OSError('symlink destination')
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix='.probe-', dir=root) as probe:
            (Path(probe) / 'write-check').write_bytes(b'probe')
    except OSError:
        raise ValueError('output_unavailable') from None


def write_report(report, root: Path, *, manifest=None, display_aliases=None):
    preflight_output(root)
    root = Path(root)
    staging = Path(tempfile.mkdtemp(prefix='.staging-', dir=root))
    final = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex)
    try:
        _write_report_files(report, staging, display_aliases=display_aliases)
        if manifest is not None:
            path = staging / 'inputs.manifest.json'
            with path.open('x', encoding='utf-8') as handle:
                os.chmod(path, 0o600)
                json.dump(manifest, handle, ensure_ascii=False, indent=2)
        staging.rename(final)
        return final
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _write_report_files(report, out, *, display_aliases=None, _literal=literal):
    # Restore only human-readable local exports, before Markdown/CSV escaping.
    # Machine data, evidence offsets, IDs and hashes always stay protected.
    from .privacy_core import REFERENCE
    aliases = display_aliases or {}
    labels = {}

    def display(value):
        def replace(match):
            ref = match.group()
            if ref in aliases:
                return aliases[ref]
            return labels.setdefault(ref, f'Фрагмент {len(labels) + 1}')
        return REFERENCE.sub(replace, str(value))

    def literal(value):
        return _literal(display(value))

    def write(name, text):
        with open(out/name, 'x', encoding='utf-8') as handle:
            os.chmod(out/name, 0o600)
            handle.write(text)
    write('report.json', json.dumps(report, ensure_ascii=False, indent=2))
    processed = len(report['ranking']['jobs'])
    missing = report['unprocessed_job_ids']
    lines = ['# Отчёт прототипа', '', f"Режим: {literal(report.get('mode', 'test'))}",
             f"Обработано вакансий: {processed}/{processed + len(missing)}",
             'Рейтинг полный.' if report['ranking']['complete'] else 'Рейтинг неполный — порядок относится только к обработанным вакансиям.',
             f"Рекомендация: {literal(report['ranking']['recommendation'])}",
             'Все рекомендации требуют проверки рекрутером. review_none_fit — гипотеза модели, не окончательный отказ.',
             'Требования не подтверждены человеком; полнота обработки не означает проверенный итог. Пакет менеджеру — черновик.',
             '', 'Порядок вакансий: сначала без выявленного нарушения обязательных требований, затем по убыванию L.',
             'При одинаковом L в одной группе по нарушению обязательных требований вакансии делят место; id определяет только порядок отображения внутри этой группы.',
             ('Политика v3: обязательная группа — 75 баллов шкалы, прочая — 25; если группа одна, ей отводятся все 100. Внутри группы единицы требований равны. Это правила команды, не подтверждённые экспертом веса.'
              if report.get('policy_version') == 'draft-2026-11-14-v3' else
              'Черновые веса: обязательное требование — 3, прочее — 1; full=1, partial=0.5, fail=0; unknown учитывается отдельно.'),
             'L — баллы по структурно сверенным основаниям / сумма весов; H дополнительно включает вес неизвестных и спорных требований. Смысл цитат проверяет рекрутер. Все значения в процентах.',
             'L/H — границы оценки при неизвестных данных, не вероятность найма.',
             'full — полное соответствие; partial — частичное соответствие; fail — явное несоответствие; unknown — информация не указана.', '']
    if report.get('privacy', {}).get('professional_information_may_be_hidden'):
        lines += ['Защита заменила названия организаций; среди них могут быть названия технологий. Сверьте профессиональные сведения с локальным оригиналом.']
    if missing:
        lines += ['Не оценены (ошибка или остановка до обработки): ' + ', '.join(literal(jid) for jid in missing), '']
    ranked = report['ranking']['jobs']
    recommendation = report['ranking']['recommendation']
    actions = {
        'review_top': 'Проверьте вакансии первого места и их доказательства перед передачей менеджеру.',
        'clarify': 'Сначала уточните неизвестные или частично подтверждённые требования у кандидата.',
        'review_none_fit': 'Проверьте выявленные обязательные несоответствия; автоматический отказ недопустим.',
        'incomplete': 'Завершите обработку пропущенных вакансий; окончательный выбор по этому отчёту невозможен.',
    }
    if recommendation == 'clarify' and any(
        j['score'].get('disputed_ids') or j['score'].get('excluded_mandatory_ids') for j in ranked
    ):
        actions['clarify'] = ('Подтверждённого соответствия недостаточно для окончательного порядка: '
                              'есть спорные доказательства или неприменённые маркеры '
                              'обязательности. Прочитайте их контекст и сравните вакансии до вывода; '
                              'автоматический отказ недопустим.')
    elif recommendation == 'clarify' and not any(
        row['status'] in {'unknown', 'partial'} for job in ranked if job['rank'] == 1
        for row in job['evaluation']['rows']
    ):
        actions['clarify'] = 'Подтверждённого соответствия недостаточно. Проверьте выявленные несоответствия и релевантность доказательств; автоматический отказ недопустим.'
    if recommendation == 'clarify' and (report.get('leader') or {}).get('state') == 'close':
        actions['clarify'] = 'Оценки близки: превосходство по проценту не установлено. Сравните вакансии по существу и зафиксируйте решение HR.'
    lines += [actions.get(recommendation, 'Проверьте результат вручную.')]
    if report.get('leader'):
        lines += ['Первое место по политике: ' + literal(report['leader']['summary'])]
    if ranked:
        label = 'Первое место' if report['ranking']['complete'] else 'Первое место среди обработанных (предварительно)'
        lines += [label + ': ' + ', '.join(literal(j['job_id']) for j in ranked if j['rank'] == 1)]
        lines += ['Сводка порядка:']
        for job in ranked:
            s = job['score']
            lines.append(f"- Место {job['rank']}: {literal(job['job_id'])}; обязательные {s['mandatory']}; L={s['lower']}, H={s['upper']}, известность={s['coverage']}%.")
    for error in report['errors']:
        lines.append(f"Ошибка: {literal(error.get('job_id') or 'все вакансии')}; стадия: {literal(error.get('stage', 'unknown'))}; код: {literal(error['code'])}.")
    lines.append('')
    records = []
    facts = {f['id']:f for f in report['facts']['items']}
    prepared_jobs = {j['job_id']:j for j in build_presentation(report)['jobs']}
    for job in report['ranking']['jobs']:
        s = job['score']
        lines += [f"## {job['rank']}. {literal(job['job_id'])}",
                  f"Оценка {s['lower']}–{s['upper']}; известность {s['coverage']}%; обязательные: {s['mandatory']}", '']
        reqs = {r['id']:r for r in job['requirements']['items']}
        prepared_rows = {r['requirement_id']:r for r in prepared_jobs[job['job_id']]['rows']}
        excluded = job.get('score_review', {}).get('excluded_mandatory_ids', [])
        if excluded:
            lines.append('Не привязанные к требованию маркеры обязательности не применены при расчёте (требование учитывается в прочей группе, требуется проверка): ' + ', '.join(literal(i) for i in excluded))
        for row in job['evaluation']['rows']:
            req = reqs[row['requirement_id']]
            evidence = ' / '.join(facts[f]['quote'] for f in row['fact_ids'])
            prepared_row = prepared_rows[req['id']]
            question = prepared_row['question']
            records.append([job['job_id'],req['id'],display_label(req),req['quote'],req['mandatory_quote'] or '',
                            row['status'],evidence,prepared_row['explanation'],question or '',
                            'conflicting_repeat_requires_review' if prepared_row['score_conflict'] else 'model_proposed_not_verified'])
            lines += [f"- {literal(display_label(req))} — **{row['status']}**.",
                      f"  Непроверенное объяснение модели: {literal(row['comment'])}",
                      f"  Требование: {literal(req['quote'])}", f"  Резюме: {literal(evidence or 'не указано')}"]
            if prepared_row['score_conflict']:
                lines.append('  Конфликт повторов: ' + literal(prepared_row['explanation']))
            check = next((r for r in job.get('evidence_check', {}).get('rows', []) if r['requirement_id'] == req['id']), None)
            if check:
                lines.append(f"  Проверка доказательства: {literal(check['state'])}; смысл остаётся непроверенным.")
                for reason in check['reasons']:
                    lines.append(f"  Проверить: {literal(reason['message'])}; контекст: {literal(reason.get('context') or 'не указан')}")
            if req['mandatory_quote']:
                lines.append(f"  Обязательность предложена моделью — подтвердите: {literal(req['mandatory_quote'])}")
            if question: lines.append(f"  Вопрос для уточнения: {literal(question)}")
        for item in (job.get('conditions') or {}).get('items', []):
            if item.get('state') == 'conflict' or item.get('check') == 'needs_review':
                sides = '; '.join(f"{who}: {literal(span['quote'])}" for who, span in
                                  (('резюме', item.get('cv_span')), ('вакансия', item.get('vacancy_span'))) if span)
                lines.append(f"- Условие {literal(item['kind'])}: {literal(item['state'])}; {sides}. Решает HR, это не отказ.")
        lines.append('')
        disputed = set(job['score'].get('disputed_ids', [])) | set(job['score'].get('conflict_ids', []))
        for status, label in [('full', 'Сильные стороны'), ('partial', 'Частичное соответствие'),
                              ('fail', 'Выявленные несоответствия'), ('unknown', 'Не хватает сведений')]:
            names = [literal(display_label(reqs[row['requirement_id']])) for row in job['evaluation']['rows']
                     if row['status'] == status and row['requirement_id'] not in disputed]
            lines.append(label + ': ' + (', '.join(names) if names else 'не выявлены по оценке'))
        if disputed:
            lines.append('Спорное доказательство, проверить до вывода: ' + ', '.join(
                literal(display_label(reqs[rid])) for rid in sorted(disputed)))
        lines += ['Риск интерпретации: статусы предложены моделью; дословность цитат не доказывает правильность вывода.',
                  'Действие рекрутера: проверить обоснования и уточнить открытые вопросы; решение остаётся за человеком.', '']
    if report['errors']: lines += ['Есть ошибки: рейтинг неполный. Подробности в report.json.']
    write('report.md', '\n'.join(lines))
    with open(out/'requirements.csv', 'x', encoding='utf-8-sig', newline='') as handle:
        os.chmod(out/'requirements.csv', 0o600)
        writer = csv.writer(handle)
        writer.writerow(['job_id','requirement_id','requirement','job_quote','mandatory_quote','status','resume_evidence','comment','question','verification'])
        # Avoid formula execution when opening untrusted model/document text in a spreadsheet.
        displayed = [[display(value) for value in row] for row in records]
        writer.writerows([["'"+v if v.lstrip().startswith(('=','+','-','@')) else v for v in row] for row in displayed])
    return out
