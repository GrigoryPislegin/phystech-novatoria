import csv
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from .contracts import Facts, Requirements, Evaluation, validate_pair
from .scoring import score, rank


def literal(value):
    """CommonMark code span: source text cannot become a link, image or raw HTML."""
    text = str(value).replace('\n', ' ').replace('\r', ' ')
    fence = '`' * (max((len(x) for x in re.findall(r'`+', text)), default=0) + 1)
    return f'{fence} {text} {fence}'


async def run_pipeline(resume, jobs, model, privacy):
    if not jobs or len(jobs) > 20 or len({j[0] for j in jobs}) != len(jobs):
        raise ValueError('invalid_job_set')
    safe_resume = await privacy.redact(resume)
    # Complete privacy preflight before the very first model call.
    safe_jobs = [(jid, await privacy.redact(text)) for jid, text in jobs]
    facts = await model.ask(Facts, 'facts', {'text':safe_resume})
    facts.validate_source(safe_resume)
    results, errors = [], []
    for jid, text in safe_jobs:
        try:
            requirements = await model.ask(Requirements, 'requirements', {'text':text})
            requirements.validate_source(text)
            evaluation = await model.ask(Evaluation, 'evaluation', {
                'requirements':requirements.model_dump(), 'facts':facts.model_dump()})
            validate_pair(requirements, facts, evaluation)
            results.append({'job_id':jid, 'requirements':requirements.model_dump(),
                            'evaluation':evaluation.model_dump(), 'score':score(requirements, evaluation),
                            'safe_source_sha256':hashlib.sha256(text.encode()).hexdigest()})
        except Exception as exc:
            # Never serialize exception messages: upstream errors may contain text/keys/DSNs.
            errors.append({'job_id':jid, 'code':'evaluation_failed', 'type':type(exc).__name__})
            # Stop after a failure: no paid retries or requests after a privacy/budget incident.
            break
    return {'schema_version':'0.1', 'facts':facts.model_dump(), 'ranking':rank(results, len(jobs)),
            'errors':errors, 'unprocessed_job_ids':[jid for jid,_ in jobs if jid not in {r['job_id'] for r in results}],
            'safe_resume_sha256':hashlib.sha256(safe_resume.encode()).hexdigest()}


def write_report(report, root: Path):
    root.mkdir(parents=True, exist_ok=True)
    out = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
    out.mkdir(mode=0o700)
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
             '', 'Порядок вакансий: сначала без выявленного нарушения обязательных требований, затем по убыванию L.',
             'При одинаковом L в одной группе по нарушению обязательных требований вакансии делят место; id определяет только порядок отображения внутри этой группы.',
             'Черновые веса: обязательное требование — 3, прочее — 1; full=1, partial=0.5, fail=0; unknown учитывается отдельно.',
             'L — подтверждённые баллы / сумма весов; H — (подтверждённые баллы + вес неизвестных требований) / сумма весов; известность — доля веса с известным статусом. Все значения в процентах.',
             'L/H — границы оценки при неизвестных данных, не вероятность найма.',
             'full — полное соответствие; partial — частичное соответствие; fail — явное несоответствие; unknown — информация не указана.', '']
    if missing:
        lines += ['Не оценены (ошибка или остановка до обработки): ' + ', '.join(literal(jid) for jid in missing), '']
    records = []
    facts = {f['id']:f for f in report['facts']['items']}
    for job in report['ranking']['jobs']:
        s = job['score']
        lines += [f"## {job['rank']}. {literal(job['job_id'])}",
                  f"Оценка {s['lower']}–{s['upper']}; известность {s['coverage']}%; обязательные: {s['mandatory']}", '']
        reqs = {r['id']:r for r in job['requirements']['items']}
        for row in job['evaluation']['rows']:
            req = reqs[row['requirement_id']]
            evidence = ' / '.join(facts[f]['quote'] for f in row['fact_ids'])
            records.append([job['job_id'],req['id'],req['text'],req['quote'],req['mandatory_quote'] or '',
                            row['status'],evidence,row['comment'],row['question'] or ''])
            lines += [f"- {literal(req['text'])} — **{row['status']}**. {literal(row['comment'])}",
                      f"  Требование: {literal(req['quote'])}", f"  Резюме: {literal(evidence or 'не указано')}"]
            if row['question']: lines.append(f"  Вопрос: {literal(row['question'])}")
        lines += ['', 'Сильные стороны: строки full; частичное соответствие: partial; пробелы/риски: fail и unknown.',
                  'Действие рекрутера: проверить обоснования и уточнить открытые вопросы; решение остаётся за человеком.', '']
    if report['errors']: lines += ['Есть ошибки: рейтинг неполный. Подробности в report.json.']
    write('report.md', '\n'.join(lines))
    with open(out/'requirements.csv', 'x', encoding='utf-8-sig', newline='') as handle:
        os.chmod(out/'requirements.csv', 0o600)
        writer = csv.writer(handle)
        writer.writerow(['job_id','requirement_id','requirement','job_quote','mandatory_quote','status','resume_evidence','comment','question'])
        # Avoid formula execution when opening untrusted model/document text in a spreadsheet.
        writer.writerows([["'"+str(v) if str(v).lstrip().startswith(('=','+','-','@')) else v for v in row] for row in records])
    return out
