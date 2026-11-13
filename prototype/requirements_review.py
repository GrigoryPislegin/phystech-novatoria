"""Recruiter confirmation of the extracted requirement list (E4).

"All vacancies were processed" and "the extracted list was checked by the recruiter" are separate
states. A list is unconfirmed by default; only an explicit recruiter action (`approve`, called by the
CLI) creates a confirmation, and the model's output format cannot produce one. The confirmation is
bound to the hash of the processed vacancy text and of the full list with mandatory markers; any
change invalidates it. Single-user CLI binding — not authentication or a digital signature.
`uncovered` is a hint for comparing with the full text, not proof that nothing was missed.

Pure and local: the integrator's CLI stores approvals in its private directory.
Not yet wired into pipeline/CLI: see docs/reviews/egor-development-handoff.md.
"""
import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from .contracts import Requirements
from .evidence import _heading_blocks, _occurrences, _segments

INTEGRATED = False
SCHEMA_VERSION = 'requirements-approval-0.1'


class _Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CanonicalRequirement(_Strict):
    id: str
    text: str
    quote: str
    mandatory_quote: str | None


class RequirementsDraft(_Strict):
    vacancy_id: str
    state: Literal['unconfirmed'] = 'unconfirmed'
    source_sha256: str
    requirements_sha256: str
    requirements: list[CanonicalRequirement]
    uncovered: list[str]


class RequirementsApproval(_Strict):
    schema_version: str
    vacancy_id: str
    source_sha256: str
    requirements_sha256: str
    requirements: list[CanonicalRequirement]
    approved_by: Literal['recruiter']
    approved_at: str


class Issue(_Strict):
    code: str
    message: str
    requirement_id: str | None = None


class ApprovalCheck(_Strict):
    vacancy_id: str
    state: Literal['confirmed', 'unconfirmed', 'stale', 'invalid']
    reasons: list[Issue]


class RunReviewSummary(_Strict):
    processing_complete: bool
    requirements_confirmed: bool
    final_allowed: bool
    unconfirmed: list[str]
    stale: list[str]
    invalid: list[str]


def source_sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _canonical(requirements):
    return sorted((CanonicalRequirement(id=r.id, text=r.text, quote=r.quote, mandatory_quote=r.mandatory_quote)
                   for r in requirements.items), key=lambda r: r.id)


def _hash_canonical(items):
    payload = json.dumps([i.model_dump() for i in items], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode()).hexdigest()


def requirements_sha256(requirements: Requirements) -> str:
    return _hash_canonical(_canonical(requirements))


def _uncovered(text, requirements):
    covered = []
    for r in requirements.items:
        for quote in [r.quote, r.mandatory_quote]:
            if quote and quote.strip():
                covered += [(p, p + len(quote)) for p in _occurrences(text, quote)]
    heading_lines = [(s, e) for s, e, _ in _heading_blocks(text)]
    out = []
    for start, end, core in _segments(text):
        if any(s <= start and end <= e for s, e in heading_lines) or not re.search(r'[^\W\d_]', core):
            continue
        if not any(s < end and start < e for s, e in covered):
            out.append(core)
    return out


def draft(vacancy_id: str, text: str, requirements: Requirements) -> RequirementsDraft:
    items = _canonical(requirements)
    return RequirementsDraft(vacancy_id=vacancy_id, source_sha256=source_sha256(text),
                             requirements_sha256=_hash_canonical(items), requirements=items,
                             uncovered=_uncovered(text, requirements))


def approve(vacancy_id: str, text: str, requirements: Requirements, approved_at: str) -> RequirementsApproval:
    """Call ONLY on an explicit recruiter action in the CLI."""
    items = _canonical(requirements)
    return RequirementsApproval(schema_version=SCHEMA_VERSION, vacancy_id=vacancy_id,
                                source_sha256=source_sha256(text), requirements_sha256=_hash_canonical(items),
                                requirements=items, approved_by='recruiter', approved_at=approved_at)


def _result(vacancy_id, state, *issues):
    return ApprovalCheck(vacancy_id=vacancy_id, state=state, reasons=list(issues))


def check(approval, vacancy_id: str, text: str, requirements: Requirements) -> ApprovalCheck:
    """approval: RequirementsApproval, a dict loaded from the CLI store, or None."""
    if approval is None:
        return _result(vacancy_id, 'unconfirmed', Issue(code='not_confirmed', message='Список не подтверждён рекрутером.'))
    if isinstance(approval, dict):
        try:
            approval = RequirementsApproval.model_validate(approval)
        except ValidationError:
            return _result(vacancy_id, 'invalid', Issue(code='malformed', message='Это не подтверждение рекрутера.'))
    if approval.schema_version != SCHEMA_VERSION:
        return _result(vacancy_id, 'invalid', Issue(code='schema_version', message='Неизвестная версия подтверждения.'))
    if approval.vacancy_id != vacancy_id:
        return _result(vacancy_id, 'invalid', Issue(code='foreign_vacancy', message='Подтверждение другой вакансии.'))
    if _hash_canonical(approval.requirements) != approval.requirements_sha256:
        return _result(vacancy_id, 'invalid', Issue(code='hash_mismatch', message='Хеш не соответствует подтверждённому списку.'))
    ids = [r.id for r in requirements.items]
    if len(ids) != len(set(ids)):
        return _result(vacancy_id, 'invalid', Issue(code='duplicate_ids', message='Повторяющиеся id требований.'))
    issues = []
    if approval.source_sha256 != source_sha256(text):
        issues.append(Issue(code='source_changed', message='Текст вакансии изменился после подтверждения.'))
    current = {r.id: r for r in _canonical(requirements)}
    approved = {r.id: r for r in approval.requirements}
    for rid in sorted(current.keys() - approved.keys()):
        issues.append(Issue(code='requirement_added', message='Добавлено требование.', requirement_id=rid))
    for rid in sorted(approved.keys() - current.keys()):
        issues.append(Issue(code='requirement_removed', message='Удалено требование.', requirement_id=rid))
    for rid in sorted(current.keys() & approved.keys()):
        now, then = current[rid], approved[rid]
        if now.mandatory_quote != then.mandatory_quote:
            issues.append(Issue(code='mandatory_changed', message='Изменилась обязательность.', requirement_id=rid))
        if (now.text, now.quote) != (then.text, then.quote):
            issues.append(Issue(code='requirement_changed', message='Изменилось требование.', requirement_id=rid))
    return _result(vacancy_id, 'stale', *issues) if issues else _result(vacancy_id, 'confirmed')


def summarize(processing_complete: bool, checks: dict, *, expected_ids: list[str]) -> RunReviewSummary:
    """Processing completeness and list confirmation are independent; neither implies the other.

    expected_ids — every vacancy of the run. A vacancy without a check counts as unconfirmed;
    a check for a vacancy outside the run is invalid.
    """
    expected = set(expected_ids)
    states = {v: 'unconfirmed' for v in expected}
    for vacancy_id, result in checks.items():
        states[vacancy_id] = result.state if vacancy_id in expected else 'invalid'
    by_state = {s: sorted(v for v, st in states.items() if st == s) for s in ('unconfirmed', 'stale', 'invalid')}
    confirmed = bool(states) and all(st == 'confirmed' for st in states.values())
    return RunReviewSummary(processing_complete=processing_complete, requirements_confirmed=confirmed,
                            final_allowed=processing_complete and confirmed, **by_state)
