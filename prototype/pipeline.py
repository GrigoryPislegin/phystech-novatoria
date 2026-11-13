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
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from .contracts import Facts, Requirements, Evaluation, validate_pair
from .scoring import score, rank
from .evidence import Source, check_pair
from . import requirements_review as review
from .errors import ModelOutputError, RunStopped, error_code
from .presentation import build_presentation, display_label, gap_question, EXPLANATIONS


class RunControl:
    """One run's deadline, cancellation and text-free stage events."""
    def __init__(self, timeout_seconds=300, progress=None):
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0 or timeout_seconds > 1800:
            raise ValueError('invalid_deadline')
        self.started = time.monotonic()
        self.deadline = self.started + timeout_seconds
        self.progress = progress
        self.cancelled = False
        self.events = []

    def cancel(self):
        self.cancelled = True

    def checkpoint(self):
        if self.cancelled:
            raise RunStopped('cancelled')
        if time.monotonic() >= self.deadline:
            raise RunStopped('deadline_exceeded')

    def emit(self, stage, job_id=None):
        event = {'stage':stage, 'job_id':job_id, 'elapsed_ms':round((time.monotonic()-self.started)*1000)}
        self.events.append(event)
        if self.progress:
            self.progress(dict(event))

    async def call(self, operation, stage, job_id=None):
        self.emit(stage, job_id)
        self.checkpoint()
        try:
            result = await asyncio.wait_for(operation(), timeout=max(0, self.deadline-time.monotonic()))
        except TimeoutError:
            raise RunStopped('deadline_exceeded') from None
        self.checkpoint()
        return result


def literal(value):
    """CommonMark code span: source text cannot become a link, image or raw HTML."""
    text = str(value).replace('\n', ' ').replace('\r', ' ')
    fence = '`' * (max((len(x) for x in re.findall(r'`+', text)), default=0) + 1)
    return f'{fence} {text} {fence}'


async def run_pipeline(resume, jobs, model, privacy, *, control=None):
    if not jobs or len(jobs) > 20 or len({j[0] for j in jobs}) != len(jobs):
        raise ValueError('invalid_job_set')
    control = control or RunControl()
    if hasattr(model, 'set_run_control'):
        model.set_run_control(control)
    safe_resume = await control.call(lambda: privacy.redact(resume), 'privacy')
    # Complete privacy preflight before the very first model call.
    safe_jobs = [(jid, await control.call(lambda: privacy.redact(text), 'privacy', jid)) for jid, text in jobs]
    cv_source = Source.of('cv', safe_resume)
    results, errors, review_checks = [], [], {}
    def finish(facts):
        missing = [jid for jid,_ in jobs if jid not in {r['job_id'] for r in results}]
        by_job = {e['job_id']:e['code'] for e in errors}
        control.emit('analysis_finished')
        report = {'schema_version':'0.1', 'facts':facts.model_dump(), 'ranking':rank(results, len(jobs)),
                'errors':errors, 'unprocessed_job_ids':missing,
                'unprocessed':[{'job_id':jid, 'reason':by_job.get(jid, by_job.get(None, 'stopped_after_error'))} for jid in missing],
                'events':control.events,
                'safe_resume_sha256':hashlib.sha256(safe_resume.encode()).hexdigest()}
        report['requirements_review'] = review.summarize(report['ranking']['complete'], review_checks,
            expected_ids=[jid for jid, _ in jobs]).model_dump()
        report['verification'] = {'requirements':'not_reviewed',
                                  'evidence':'quotes_checked_semantics_unverified',
                                  'final_allowed':False}
        report['presentation'] = build_presentation(report)
        return report
    stage = 'facts'
    try:
        facts = await control.call(lambda: model.ask(Facts, 'facts', {'text':safe_resume}), stage)
        stage = 'facts_validation'
        facts.validate_source(safe_resume)
    except Exception as exc:
        errors.append({'job_id':None, 'code':error_code(exc, stage), 'stage':stage, 'type':type(exc).__name__})
        return finish(Facts(items=[]))
    for jid, text in safe_jobs:
        stage = 'requirements'
        try:
            requirements = await control.call(lambda: model.ask(Requirements, 'requirements', {'text':text}), stage, jid)
            stage = 'requirements_validation'
            requirements.validate_source(text)
            stage = 'evaluation'
            evaluation = await control.call(lambda: model.ask(Evaluation, 'evaluation', {
                'requirements':requirements.model_dump(), 'facts':facts.model_dump()}), stage, jid)
            stage = 'evaluation_validation'
            validate_pair(requirements, facts, evaluation)
            evidence = check_pair(requirements, facts, evaluation, cv_source, Source.of(jid, text))
            if evidence.has_invalid:
                raise ModelOutputError('invalid_evidence')
            review_checks[jid] = review.check(None, jid, text, requirements)
            disputed_mandatory = {m.requirement_id for m in evidence.mandatory if m.state == 'needs_review'}
            score_requirements = Requirements(items=[r.model_copy(update={'mandatory_quote':None})
                if r.id in disputed_mandatory else r for r in requirements.items])
            results.append({'job_id':jid, 'requirements':requirements.model_dump(),
                            'evidence_check':evidence.model_dump(),
                            'requirements_draft':review.draft(jid, text, requirements).model_dump(),
                            'requirements_review':review_checks[jid].model_dump(),
                            'evaluation':evaluation.model_dump(), 'score':score(score_requirements, evaluation),
                            'score_review':{'excluded_mandatory_ids':sorted(disputed_mandatory),
                                'rule':'structurally_unbound_mandatory_uses_regular_weight',
                                'version':'mandatory-structure-0.1'},
                            'safe_source_sha256':hashlib.sha256(text.encode()).hexdigest()})
        except Exception as exc:
            # Never serialize exception messages: upstream errors may contain text/keys/DSNs.
            code = error_code(exc, stage)
            errors.append({'job_id':jid, 'code':code, 'stage':stage, 'type':type(exc).__name__})
            # Only known output-validation failures are recoverable, without retry.
            if code != 'model_invalid':
                break
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


def write_report(report, root: Path, *, manifest=None):
    preflight_output(root)
    root = Path(root)
    staging = Path(tempfile.mkdtemp(prefix='.staging-', dir=root))
    final = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex)
    try:
        _write_report_files(report, staging)
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


def _write_report_files(report, out):
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
             'Черновые веса: обязательное требование — 3, прочее — 1; full=1, partial=0.5, fail=0; unknown учитывается отдельно.',
             'L — подтверждённые баллы / сумма весов; H — (подтверждённые баллы + вес неизвестных требований) / сумма весов; известность — доля веса с известным статусом. Все значения в процентах.',
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
    if recommendation == 'clarify' and not any(
        row['status'] in {'unknown', 'partial'} for job in ranked if job['rank'] == 1
        for row in job['evaluation']['rows']
    ):
        actions['clarify'] = 'Подтверждённого соответствия недостаточно. Проверьте выявленные несоответствия и релевантность доказательств; автоматический отказ недопустим.'
    lines += [actions.get(recommendation, 'Проверьте результат вручную.')]
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
    for job in report['ranking']['jobs']:
        s = job['score']
        lines += [f"## {job['rank']}. {literal(job['job_id'])}",
                  f"Оценка {s['lower']}–{s['upper']}; известность {s['coverage']}%; обязательные: {s['mandatory']}", '']
        reqs = {r['id']:r for r in job['requirements']['items']}
        excluded = job.get('score_review', {}).get('excluded_mandatory_ids', [])
        if excluded:
            lines.append('Не привязанные к требованию маркеры обязательности не применены при расчёте (вес 1, требуется проверка): ' + ', '.join(literal(i) for i in excluded))
        for row in job['evaluation']['rows']:
            req = reqs[row['requirement_id']]
            evidence = ' / '.join(facts[f]['quote'] for f in row['fact_ids'])
            question = gap_question(row['status'], req['quote'])
            records.append([job['job_id'],req['id'],display_label(req),req['quote'],req['mandatory_quote'] or '',
                            row['status'],evidence,EXPLANATIONS[row['status']],question or '', 'model_proposed_not_verified'])
            lines += [f"- {literal(display_label(req))} — **{row['status']}**.",
                      f"  Непроверенное объяснение модели: {literal(row['comment'])}",
                      f"  Требование: {literal(req['quote'])}", f"  Резюме: {literal(evidence or 'не указано')}"]
            check = next((r for r in job.get('evidence_check', {}).get('rows', []) if r['requirement_id'] == req['id']), None)
            if check:
                lines.append(f"  Проверка доказательства: {literal(check['state'])}; смысл остаётся непроверенным.")
                for reason in check['reasons']:
                    lines.append(f"  Проверить: {literal(reason['message'])}; контекст: {literal(reason.get('context') or 'не указан')}")
            if req['mandatory_quote']:
                lines.append(f"  Обязательность предложена моделью — подтвердите: {literal(req['mandatory_quote'])}")
            if question: lines.append(f"  Вопрос для уточнения: {literal(question)}")
        lines.append('')
        for status, label in [('full', 'Сильные стороны'), ('partial', 'Частичное соответствие'),
                              ('fail', 'Выявленные несоответствия'), ('unknown', 'Не хватает сведений')]:
            names = [literal(display_label(reqs[row['requirement_id']])) for row in job['evaluation']['rows'] if row['status'] == status]
            lines.append(label + ': ' + (', '.join(names) if names else 'не выявлены по оценке'))
        lines += ['Риск интерпретации: статусы предложены моделью; дословность цитат не доказывает правильность вывода.',
                  'Действие рекрутера: проверить обоснования и уточнить открытые вопросы; решение остаётся за человеком.', '']
    if report['errors']: lines += ['Есть ошибки: рейтинг неполный. Подробности в report.json.']
    write('report.md', '\n'.join(lines))
    with open(out/'requirements.csv', 'x', encoding='utf-8-sig', newline='') as handle:
        os.chmod(out/'requirements.csv', 0o600)
        writer = csv.writer(handle)
        writer.writerow(['job_id','requirement_id','requirement','job_quote','mandatory_quote','status','resume_evidence','comment','question','verification'])
        # Avoid formula execution when opening untrusted model/document text in a spreadsheet.
        writer.writerows([["'"+str(v) if str(v).lstrip().startswith(('=','+','-','@')) else v for v in row] for row in records])
    return out
