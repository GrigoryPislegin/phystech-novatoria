"""Recruiter confirmation of the extracted requirement list (E4).

"Every vacancy was processed" and "the recruiter checked the extracted list" are separate states.
A list is unconfirmed by default. Only an explicit recruiter action (`approve`, called by the CLI)
creates a confirmation, and the model's output format cannot be read as one. The confirmation is
bound to the hash of the processed vacancy text and of the full list with mandatory markers, so any
change invalidates it. This is a single-user CLI binding, not authentication or a signature.
`uncovered` is a hint for comparing against the full text, not proof that nothing was missed.

Pure and local; the integrator's CLI stores approvals in its private directory.
Drafts and checks are included in pipeline reports; interactive approval UI is a separate task.
"""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from .contracts import Requirements
from .evidence import layout, occurrences, sha256_text

INTEGRATED = True
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


source_sha256 = sha256_text


def _canonical(requirements: Requirements) -> list[CanonicalRequirement]:
    items = (CanonicalRequirement(id=r.id, text=r.text, quote=r.quote, mandatory_quote=r.mandatory_quote)
             for r in requirements.items)
    return sorted(items, key=lambda r: r.id)


def _hash(items: list[CanonicalRequirement]) -> str:
    payload = [i.model_dump() for i in items]
    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')))


def requirements_sha256(requirements: Requirements) -> str:
    return _hash(_canonical(requirements))


def _uncovered(text: str, requirements: Requirements) -> list[str]:
    """Sentences no requirement or mandatory quote touches; headings and bare numbers are skipped."""
    quotes = [q for r in requirements.items for q in (r.quote, r.mandatory_quote) if q]
    covered = [(p, p + len(q)) for q in quotes for p in occurrences(text, q)]
    lay = layout(text)
    return [s.text for s in lay.sentences
            if any(c.isalpha() for c in s.text)
            and not any(h.start <= s.start and s.end <= h.end for h in lay.headings)
            and not any(a < s.end and s.start < b for a, b in covered)]


def draft(vacancy_id: str, text: str, requirements: Requirements) -> RequirementsDraft:
    items = _canonical(requirements)
    return RequirementsDraft(vacancy_id=vacancy_id, source_sha256=source_sha256(text), requirements_sha256=_hash(items),
                             requirements=items, uncovered=_uncovered(text, requirements))


def approve(vacancy_id: str, text: str, requirements: Requirements, approved_at: str) -> RequirementsApproval:
    """Call only on an explicit recruiter action in the CLI."""
    if len({r.id for r in requirements.items}) != len(requirements.items):
        raise ValueError('duplicate_requirement_ids')
    items = _canonical(requirements)
    return RequirementsApproval(schema_version=SCHEMA_VERSION, vacancy_id=vacancy_id,
                                source_sha256=source_sha256(text), requirements_sha256=_hash(items),
                                requirements=items, approved_by='recruiter', approved_at=approved_at)


def _invalid(vacancy_id: str, code: str, message: str) -> ApprovalCheck:
    return ApprovalCheck(vacancy_id=vacancy_id, state='invalid', reasons=[Issue(code=code, message=message)])


def _changes(approval: RequirementsApproval, text: str, requirements: Requirements) -> list[Issue]:
    issues = []
    if approval.source_sha256 != source_sha256(text):
        issues.append(Issue(code='source_changed', message='Текст вакансии изменился после подтверждения.'))
    now = {r.id: r for r in _canonical(requirements)}
    then = {r.id: r for r in approval.requirements}
    issues += [Issue(code='requirement_added', message='Добавлено требование.', requirement_id=rid)
               for rid in sorted(now.keys() - then.keys())]
    issues += [Issue(code='requirement_removed', message='Удалено требование.', requirement_id=rid)
               for rid in sorted(then.keys() - now.keys())]
    for rid in sorted(now.keys() & then.keys()):
        if now[rid].mandatory_quote != then[rid].mandatory_quote:
            issues.append(Issue(code='mandatory_changed', message='Изменилась обязательность.', requirement_id=rid))
        if (now[rid].text, now[rid].quote) != (then[rid].text, then[rid].quote):
            issues.append(Issue(code='requirement_changed', message='Изменилось требование.', requirement_id=rid))
    return issues


def check(approval: RequirementsApproval | dict | None, vacancy_id: str, text: str,
          requirements: Requirements) -> ApprovalCheck:
    """approval: an approval object, a dict loaded from the CLI store, or None."""
    if approval is None:
        return ApprovalCheck(vacancy_id=vacancy_id, state='unconfirmed',
                             reasons=[Issue(code='not_confirmed', message='Список не подтверждён рекрутером.')])
    if isinstance(approval, dict):
        try:
            approval = RequirementsApproval.model_validate(approval)
        except ValidationError:
            return _invalid(vacancy_id, 'malformed', 'Это не подтверждение рекрутера.')
    if approval.schema_version != SCHEMA_VERSION:
        return _invalid(vacancy_id, 'schema_version', 'Неизвестная версия подтверждения.')
    if approval.vacancy_id != vacancy_id:
        return _invalid(vacancy_id, 'foreign_vacancy', 'Подтверждение другой вакансии.')
    if _hash(approval.requirements) != approval.requirements_sha256:
        return _invalid(vacancy_id, 'hash_mismatch', 'Хеш не соответствует подтверждённому списку.')
    ids = [r.id for r in requirements.items]
    saved_ids = [r.id for r in approval.requirements]
    if len(ids) != len(set(ids)) or len(saved_ids) != len(set(saved_ids)):
        return _invalid(vacancy_id, 'duplicate_ids', 'Повторяющиеся id требований.')
    issues = _changes(approval, text, requirements)
    return ApprovalCheck(vacancy_id=vacancy_id, state='stale' if issues else 'confirmed', reasons=issues)


def summarize(processing_complete: bool, checks: dict[str, ApprovalCheck], *,
              expected_ids: list[str]) -> RunReviewSummary:
    """Processing completeness and list confirmation are independent; neither implies the other.

    expected_ids lists every vacancy of the run: one without a check counts as unconfirmed,
    a check for a vacancy outside the run is invalid.
    """
    expected = set(expected_ids)
    states = dict.fromkeys(expected, 'unconfirmed')
    for vacancy_id, result in checks.items():
        states[vacancy_id] = result.state if vacancy_id in expected and result.vacancy_id == vacancy_id else 'invalid'
    by_state = {s: sorted(v for v, st in states.items() if st == s) for s in ('unconfirmed', 'stale', 'invalid')}
    confirmed = bool(states) and all(st == 'confirmed' for st in states.values())
    return RunReviewSummary(processing_complete=processing_complete, requirements_confirmed=confirmed,
                            final_allowed=processing_complete and confirmed, **by_state)
