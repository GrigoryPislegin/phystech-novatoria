"""What the recruiter should check first, and why (E8). A pure function over a finished report.

`build_review_queue(report)` turns signals the report already carries into typed review items.
It calls no model and adds no facts. A row gets an item only for a concrete signal: a row whose
meaning is merely unproven by the algorithm stays `model_proposed` and is not queued.

Priority:
1. integrity — a technically wrong or unresolved source, a failed or incomplete run, a stale or
   invalid confirmation; a click does not close these;
2. a possibly wrong mandatory condition or negative conclusion (a disputed fail, a verified fail on a
   mandatory requirement, an unbound mandatory marker), and possible loss of professional data by
   the privacy step;
3. conflicts of working conditions (E5), shown to HR, never an automatic rejection;
4. other clarifications: unknown mandatory requirements, other disputed rows (a bullet under a list
   heading, a fragment quote), the unconfirmed requirement list, vacancy text no requirement covers.
Within a priority the order is deterministic (job, requirement, reason); it is not hiring importance.

Item ids are stable: they depend on the processed resume and vacancy hashes, job id, requirement id
(or condition kind) and reason, not on the order of jobs or files, and the same signal never yields
two items. A decision about an item must also be bound to the report version (see the E8b contract):
a rerun may change the model's verdict while keeping the id.
Not wired into the pipeline yet (INTEGRATED = False).
"""
import hashlib
from collections import Counter
from typing import Literal

from .contracts import StrictModel
from .evidence import MandatoryCheck, RowCheck

INTEGRATED = False
SCHEMA_VERSION = 'review-queue-0.1'

ReasonCode = Literal[
    'processing_error', 'incomplete_run', 'invalid_evidence', 'ambiguous_location', 'requirements_stale',
    'mandatory_unbound', 'disputed_negative', 'mandatory_fail', 'privacy_may_hide',
    'condition_conflict',
    'mandatory_unknown', 'disputed_evidence', 'requirements_unconfirmed', 'uncovered_text']
Kind = Literal['integrity', 'interpretation', 'missing_info', 'conditions', 'requirements']
Action = Literal['complete_run', 'fix_source', 'read_context', 'check_list', 'ask_candidate',
                 'decide_condition', 'compare_with_original']

# reason -> (priority, kind, action, explanation)
REASONS: dict[str, tuple[int, str, str, str]] = {
    'processing_error': (1, 'integrity', 'complete_run',
                         'Вакансия не обработана; её место в рейтинге неизвестно.'),
    'incomplete_run': (1, 'integrity', 'complete_run',
                       'Обработаны не все вакансии; окончательный общий рейтинг невозможен.'),
    'invalid_evidence': (1, 'integrity', 'fix_source',
                         'Ссылка или цитата не проходит проверку источника; кнопкой это не закрывается.'),
    'ambiguous_location': (1, 'integrity', 'read_context',
                           'Цитата стоит в разных контекстах резюме; какой из них имела в виду модель, неизвестно.'),
    'requirements_stale': (1, 'integrity', 'check_list',
                           'Подтверждение списка требований устарело или не подходит к этой вакансии.'),
    'mandatory_unbound': (2, 'interpretation', 'check_list',
                          'Обязательность не привязана к требованию структурно; в балле она не применена.'),
    'disputed_negative': (2, 'interpretation', 'read_context',
                          'Спорное доказательство у отрицательного вывода (fail).'),
    'mandatory_fail': (2, 'interpretation', 'read_context',
                       'Модель предложила несоответствие обязательному требованию; это исключает вакансию.'),
    'privacy_may_hide': (2, 'missing_info', 'compare_with_original',
                         'Защита данных могла заменить названия технологий; «не указано» может быть потерей данных.'),
    'condition_conflict': (3, 'conditions', 'decide_condition',
                           'Условия работы в резюме и вакансии расходятся; решает HR, это не отказ.'),
    'mandatory_unknown': (4, 'missing_info', 'ask_candidate',
                          'Сведений по обязательному требованию нет; это не несоответствие.'),
    'disputed_evidence': (4, 'interpretation', 'read_context',
                          'Структура доказательства спорная (например, пункт списка или часть предложения).'),
    'requirements_unconfirmed': (4, 'requirements', 'check_list',
                                 'Список требований не подтверждён рекрутером.'),
    'uncovered_text': (4, 'requirements', 'check_list',
                       'Часть текста вакансии не попала ни в одно требование; проверьте пропуски.'),
}


class SourceRef(StrictModel):
    source: Literal['cv', 'vacancy']
    quote: str
    sentence: str | None  # None when the report does not give one; never invented
    heading: str | None
    fact_id: str | None


class ReviewItem(StrictModel):
    id: str
    job_id: str | None  # None for run-level items
    requirement_id: str | None
    condition_kind: str | None  # E5 condition items; never mixed with model requirement ids
    reason_code: ReasonCode
    kind: Kind
    priority: int
    action: Action
    explanation: str
    refs: list[SourceRef]
    contexts: list[str]  # e.g. the different CV contexts of an ambiguous quote
    detail_codes: list[str]  # underlying E3/E4/E5 codes


class ReviewQueue(StrictModel):
    schema_version: Literal['review-queue-0.1'] = SCHEMA_VERSION
    policy_version: str | None
    model_status: Literal['model_proposed'] = 'model_proposed'  # queued or not, statuses stay model proposals
    items: list[ReviewItem]
    by_reason: dict[str, int]
    by_job: dict[str, int]  # '' is the run level
    by_priority: dict[str, int]


def _item_id(*parts: str | None) -> str:
    return hashlib.sha256('\x1f'.join(p or '' for p in parts).encode()).hexdigest()[:16]


class _Builder:
    def __init__(self):
        self.items: dict[str, ReviewItem] = {}

    def add(self, reason: str, scope: str, job_id: str | None = None, requirement_id: str | None = None, *,
            condition_kind: str | None = None, refs=(), contexts=(), details=()):
        priority, kind, action, explanation = REASONS[reason]
        item_id = _item_id(scope, job_id, requirement_id, condition_kind, reason)
        old = self.items.get(item_id)
        if old is not None:  # one item per signal; merge sources from repeated or related evidence
            refs = [*old.refs, *(r for r in refs if r not in old.refs)]
            contexts = [*old.contexts, *(c for c in contexts if c not in old.contexts)]
            details = [*old.detail_codes, *(d for d in details if d not in old.detail_codes)]
        self.items[item_id] = ReviewItem(
            id=item_id, job_id=job_id, requirement_id=requirement_id, condition_kind=condition_kind,
            reason_code=reason, kind=kind, priority=priority, action=action, explanation=explanation,
            refs=list(refs), contexts=list(contexts), detail_codes=list(details))


def _cv_refs(row: RowCheck | None, fact_ids: list[str], facts: dict[str, str]) -> list[SourceRef]:
    """E3 spans with sentence and heading; without a check, the fact quotes as given in the report."""
    if row is not None and row.evidence:
        refs = [SourceRef(source='cv', quote=s.quote, sentence=s.sentence, heading=s.heading, fact_id=None)
                for s in row.evidence]
        if len(refs) == len(fact_ids):
            refs = [r.model_copy(update={'fact_id': f}) for r, f in zip(refs, fact_ids)]
        return refs
    return [SourceRef(source='cv', quote=facts[f], sentence=None, heading=None, fact_id=f)
            for f in fact_ids if f in facts]


def _contexts(row: RowCheck | None) -> list[str]:
    reasons = row.reasons if row is not None else []
    return [c for r in reasons if r.code == 'ambiguous_location' and r.context for c in r.context.split(' | ')]


def _span_ref(source: str, span) -> SourceRef | None:
    if not isinstance(span, dict) or not span.get('quote'):
        return None
    return SourceRef(source=source, quote=span['quote'], sentence=span.get('sentence'), heading=span.get('heading'),
                     fact_id=None)


def _condition_items(b: _Builder, scope: str, jid: str, conditions: dict) -> None:
    """E5 ConditionsCheck (PR #8): items[{kind, state, check, findings, cv_span, vacancy_span}],
    conflicts[], has_invalid. A malformed entry is an integrity item, never silently skipped."""
    items = conditions.get('items')
    if not isinstance(items, list):
        b.add('invalid_evidence', scope, jid, condition_kind='conditions', details=['malformed_conditions'])
        return
    seen = set()
    for raw in items:
        kind = raw.get('kind') if isinstance(raw, dict) else None
        if not kind:
            b.add('invalid_evidence', scope, jid, condition_kind='conditions', details=['malformed_conditions'])
            continue
        codes = [f.get('code') for f in raw.get('findings', []) if isinstance(f, dict)]
        refs = [r for r in (_span_ref('cv', raw.get('cv_span')), _span_ref('vacancy', raw.get('vacancy_span'))) if r]
        if raw.get('check') == 'invalid':
            b.add('invalid_evidence', scope, jid, condition_kind=kind, refs=refs, details=codes)
        elif raw.get('state') == 'conflict' or 'unknown_with_both_sides' in codes:
            b.add('condition_conflict', scope, jid, condition_kind=kind, refs=refs, details=codes)
            seen.add(kind)
    for kind in conditions.get('conflicts', []):  # a conflict listed at the top level is never lost
        if kind not in seen:
            b.add('condition_conflict', scope, jid, condition_kind=kind, details=['condition_conflict'])
    if conditions.get('has_invalid') and not any(
            i.job_id == jid and i.reason_code == 'invalid_evidence' and i.condition_kind for i in b.items.values()):
        b.add('invalid_evidence', scope, jid, condition_kind='conditions', details=['has_invalid'])


def _job_items(b: _Builder, resume: str, job: dict, facts: dict[str, str]) -> None:
    jid = job['job_id']
    scope = f"{resume}|{job.get('safe_source_sha256', '')}"
    requirements = {r['id']: r for r in job['requirements']['items']}
    score = job.get('score', {})
    excluded = set(score.get('excluded_mandatory_ids', [])) | set(
        job.get('score_review', {}).get('excluded_mandatory_ids', []))
    applied = {rid for rid, r in requirements.items() if r['mandatory_quote']} - excluded
    checks = job.get('evidence_check') or {}
    row_checks = {c['requirement_id']: RowCheck.model_validate(c) for c in checks.get('rows', [])}
    disputed_v2 = set(score.get('disputed_ids', []))

    def vacancy_ref(rid):
        return SourceRef(source='vacancy', quote=requirements[rid]['quote'], sentence=None, heading=None, fact_id=None)

    for row in job['evaluation']['rows']:
        rid, status = row['requirement_id'], row['status']
        if rid not in requirements:
            b.add('invalid_evidence', scope, jid, rid, details=['unknown_requirement_id'])
            continue
        check = row_checks.get(rid)
        state = check.state if check is not None else 'unchecked'
        if state == 'structure_ok' and rid in disputed_v2:
            state = 'needs_review'
        codes = [r.code for r in check.reasons] if check is not None else []
        refs = [vacancy_ref(rid)] + _cv_refs(check, row['fact_ids'], facts)
        if state == 'invalid':
            b.add('invalid_evidence', scope, jid, rid, refs=refs, details=codes)
        elif state == 'needs_review' and 'ambiguous_location' in codes:  # the source itself is unresolved
            b.add('ambiguous_location', scope, jid, rid, refs=refs, contexts=_contexts(check), details=codes)
        elif state == 'needs_review':
            b.add('disputed_negative' if status == 'fail' else 'disputed_evidence', scope, jid, rid, refs=refs,
                  details=codes)
        elif status == 'fail' and rid in applied:  # verified structure or no check at all: the excluding row
            b.add('mandatory_fail', scope, jid, rid, refs=refs, details=codes or ['evidence_not_checked'])
        if status == 'unknown' and rid in applied:
            b.add('mandatory_unknown', scope, jid, rid, refs=[vacancy_ref(rid)])

    for raw in checks.get('mandatory', []):
        check = MandatoryCheck.model_validate(raw)
        codes = [r.code for r in check.reasons]
        if check.requirement_id not in requirements:
            b.add('invalid_evidence', scope, jid, check.requirement_id, details=['unknown_requirement_id'])
            continue
        marker = requirements[check.requirement_id]['mandatory_quote']
        refs = [SourceRef(source='vacancy', quote=marker, sentence=check.context, heading=None, fact_id=None)
                ] if marker else []
        if check.state == 'invalid':
            b.add('invalid_evidence', scope, jid, check.requirement_id, refs=refs, details=codes)
        elif check.state == 'needs_review' or check.requirement_id in excluded:
            b.add('mandatory_unbound', scope, jid, check.requirement_id, refs=refs, details=codes)

    review = job.get('requirements_review') or {}
    if review.get('state') in {'stale', 'invalid'} or review.get('vacancy_id') not in (None, jid):
        b.add('requirements_stale', scope, jid, details=[r['code'] for r in review.get('reasons', [])])
    else:  # a 'confirmed' field in the report proves nothing; confirmation is a recorded decision (E8b)
        b.add('requirements_unconfirmed', scope, jid)
    uncovered = (job.get('requirements_draft') or {}).get('uncovered', [])
    if uncovered:
        b.add('uncovered_text', scope, jid, contexts=uncovered)
    if job.get('conditions') is not None:
        _condition_items(b, scope, jid, job['conditions'])


def build_review_queue(report: dict) -> ReviewQueue:
    b = _Builder()
    resume = report.get('safe_resume_sha256', '')
    jobs = report['ranking']['jobs']
    facts = {f['id']: f['quote'] for f in report.get('facts', {}).get('items', [])}
    unprocessed = report.get('unprocessed', [])
    run_scope = '|'.join([resume, *sorted(f"{j['job_id']}:{j.get('safe_source_sha256', '')}" for j in jobs),
                          *sorted(e['job_id'] for e in unprocessed)])
    for entry in unprocessed:
        b.add('processing_error', run_scope, entry['job_id'], details=[entry.get('reason', 'unknown')])
    for error in report.get('errors', []):
        if error.get('job_id') is None:
            b.add('processing_error', run_scope, details=[error.get('code', 'unknown')])
    if not report['ranking'].get('complete', False):
        b.add('incomplete_run', run_scope)
    if (report.get('privacy') or {}).get('professional_information_may_be_hidden'):
        b.add('privacy_may_hide', run_scope)
    for job in jobs:
        _job_items(b, resume, job, facts)

    items = sorted(b.items.values(), key=lambda i: (i.priority, i.job_id or '', i.requirement_id or '',
                                                     i.condition_kind or '', i.reason_code, i.id))
    versions = {j.get('score', {}).get('policy_version') for j in jobs} - {None}
    return ReviewQueue(
        policy_version=versions.pop() if len(versions) == 1 else None, items=items,
        by_reason=dict(sorted(Counter(i.reason_code for i in items).items())),
        by_job=dict(sorted(Counter(i.job_id or '' for i in items).items())),
        by_priority=dict(sorted(Counter(str(i.priority) for i in items).items())))
