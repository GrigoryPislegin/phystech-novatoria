"""Recruiter decisions and handoff readiness of one vacancy (E8b). A pure function.

`assess_handoff(report, decisions, job_id)` reads a finished report, the review queue it implies
(`build_review_queue`) and the recruiter's decisions recorded by the service. It writes nothing and
never changes the model's evaluation: decisions are a separate layer on top of it.

- A decision counts only on the exact versions it was made on: report, resume, vacancy source,
  requirement list and policy. Otherwise it is stale and is not inherited by a new report or by
  another candidate on the same vacancy.
- `draft` and `reviewed_for_handoff` differ: the second needs a requirement list confirmed by a
  `confirm_requirements` decision (the report's own E4 field is never trusted), every
  queue item of the vacancy closed, no blockers and an explicit `mark_for_handoff`. It records the
  recruiter's decision on that version, not a proven match.
- Blockers (failed or incomplete run, invalid or ambiguous source, stale confirmation) are never
  closed by a click. `read_context` acknowledges an item and changes no status: unknown stays
  unknown, a disputed mandatory marker stays outside the hard group. `accept_condition` keeps the
  conflict visible as an accepted exception.
- An item of one vacancy filed under another, a decision id reused with different content (across
  the whole store) or a record that is not a recruiter action recorded by the service makes the
  assessment invalid; a malformed record cannot be attributed, so it fails every assessment closed. Two identical
  decisions are one decision. There is no bulk approval and no automatic rejection.
Not wired into the pipeline or the service yet (INTEGRATED = False).
"""
import hashlib
import json
from typing import Literal

from pydantic import ValidationError

from .contracts import Requirements, StrictModel
from .requirements_review import requirements_sha256
from .review_queue import ReviewItem, build_review_queue

INTEGRATED = False

Action = Literal['confirm_requirements', 'read_context', 'accept_condition', 'mark_for_handoff']
State = Literal['draft', 'reviewed_for_handoff', 'blocked', 'stale', 'invalid']

BLOCKERS = {'processing_error', 'incomplete_run', 'invalid_evidence', 'ambiguous_location', 'requirements_stale'}
# The analysis content a decision is made on. Review-layer fields (E4 checks, verification, presentation),
# timings and usage are left out, so recording a decision or an approval does not make other decisions stale.
_REPORT_FIELDS = ('run_id', 'safe_resume_sha256', 'facts', 'errors', 'unprocessed', 'privacy', 'profile')
_JOB_FIELDS = ('job_id', 'safe_source_sha256', 'requirements', 'evaluation', 'evidence_check', 'score',
               'score_review', 'requirements_draft', 'conditions')
# reason -> the only action that closes it
CLOSED_BY = {
    'requirements_unconfirmed': 'confirm_requirements',
    'uncovered_text': 'confirm_requirements',
    'mandatory_unbound': 'read_context',
    'disputed_negative': 'read_context',
    'mandatory_fail': 'read_context',
    'privacy_may_hide': 'read_context',
    'mandatory_unknown': 'read_context',
    'disputed_evidence': 'read_context',
    'condition_conflict': 'accept_condition',
    'condition_review': 'read_context',
    'profile_review': 'read_context',
}
_VERSIONED = ('report_sha256', 'resume_sha256', 'source_sha256', 'requirements_sha256', 'policy_version')


class Decision(StrictModel):
    """A recruiter action recorded by the service on one version of the report."""
    decision_id: str
    job_id: str
    item_id: str | None  # required for read_context / accept_condition
    action: Action
    report_sha256: str
    resume_sha256: str
    source_sha256: str
    requirements_sha256: str
    policy_version: str
    decided_by: Literal['recruiter']
    recorded_by: Literal['service']
    decided_at: str


class Issue(StrictModel):
    code: str
    decision_id: str | None = None
    item_id: str | None = None


class HandoffAssessment(StrictModel):
    job_id: str
    state: State
    model_status: Literal['model_proposed'] = 'model_proposed'  # decisions never change evaluation statuses
    requirements_confirmed: bool  # only a valid confirm_requirements decision; a report field is not trusted
    processing_complete: bool  # every vacancy processed; says nothing about the meaning of the rows
    blockers: list[str]
    open_items: list[str]
    acknowledged: list[str]  # read by the recruiter; statuses unchanged (unknown stays unknown)
    accepted_exceptions: list[str]  # condition conflicts HR accepted; they stay in the report
    reasons: list[Issue]


def report_sha256(report: dict) -> str:
    """Version of the analysis a decision is made on: resume, facts, errors, privacy summary and,
    per job, requirements, evaluation, evidence, score and conditions. Order of jobs does not matter."""
    content = {k: report.get(k) for k in _REPORT_FIELDS}
    content['jobs'] = sorted(({k: j.get(k) for k in _JOB_FIELDS} for j in report['ranking']['jobs']),
                             key=lambda j: j['job_id'])
    canon = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canon.encode()).hexdigest()


def closing_decision(reason_code: str) -> Action | None:
    """The decision that closes a queue item with this reason; None for blockers."""
    return CLOSED_BY.get(reason_code)


def current_versions(report: dict, job: dict) -> dict[str, str]:
    """The versions a decision about `job` must carry to count."""
    return {'report_sha256': report_sha256(report), 'resume_sha256': report.get('safe_resume_sha256', ''),
            'source_sha256': job.get('safe_source_sha256', ''),
            'requirements_sha256': requirements_sha256(Requirements.model_validate(job['requirements'])),
            'policy_version': job.get('score', {}).get('policy_version', '')}


def _parse(raw, issues: list[Issue]) -> Decision | None:
    if isinstance(raw, Decision):
        return raw
    try:
        return Decision.model_validate(raw)
    except ValidationError:
        decision_id = raw.get('decision_id') if isinstance(raw, dict) else None
        issues.append(Issue(code='not_a_service_decision', decision_id=decision_id))
        return None


def assess_handoff(report: dict, decisions: list, job_id: str) -> HandoffAssessment:
    jobs = {j['job_id']: j for j in report['ranking']['jobs']}
    queue = build_review_queue(report)
    processing_complete = not any(i.reason_code in {'incomplete_run', 'processing_error'} for i in queue.items)
    if job_id not in jobs:
        if any(e.get('job_id') == job_id for e in report.get('unprocessed', [])):
            item = next(i for i in queue.items if i.job_id == job_id)
            return HandoffAssessment(job_id=job_id, state='blocked', requirements_confirmed=False,
                                     processing_complete=False, blockers=[item.id], open_items=[], acknowledged=[],
                                     accepted_exceptions=[], reasons=[Issue(code='processing_error', item_id=item.id)])
        raise ValueError('unknown_job')

    job = jobs[job_id]
    versions = current_versions(report, job)
    owner = {i.id: i.job_id for i in queue.items}
    # Run-level items (incomplete run, privacy) concern every vacancy of the run.
    items: dict[str, ReviewItem] = {i.id: i for i in queue.items if i.job_id in (job_id, None)}
    issues: list[Issue] = []

    # Decision ids are unique across the whole store: a reused id with other content is a store error.
    by_id: dict[str, Decision] = {}
    for raw in decisions:
        decision = _parse(raw, issues)
        if decision is None:  # unattributable, so it fails every assessment closed
            continue
        known = by_id.get(decision.decision_id)
        if known is not None and known != decision:
            issues.append(Issue(code='duplicate_decision', decision_id=decision.decision_id))
        by_id.setdefault(decision.decision_id, decision)

    valid: list[Decision] = []
    stale = False
    for decision in sorted(by_id.values(), key=lambda d: d.decision_id):
        # run-level items and ids unknown to this queue belong to whichever job the decision names
        item_owner = owner.get(decision.item_id) or decision.job_id
        if decision.job_id != job_id and item_owner != job_id:
            continue  # another vacancy's decision
        if decision.job_id != item_owner:  # an item of one vacancy filed under another
            issues.append(Issue(code='foreign_job', decision_id=decision.decision_id, item_id=decision.item_id))
            continue
        changed = [k for k in _VERSIONED if getattr(decision, k) != versions[k]]
        if changed:
            stale = True
            issues += [Issue(code='stale_' + k, decision_id=decision.decision_id, item_id=decision.item_id)
                       for k in changed]
            continue
        if decision.item_id is not None and decision.item_id not in items:
            stale = True
            issues.append(Issue(code='unknown_item', decision_id=decision.decision_id, item_id=decision.item_id))
            continue
        if decision.action in {'read_context', 'accept_condition'} and decision.item_id is None:
            issues.append(Issue(code='missing_item', decision_id=decision.decision_id))
            continue
        valid.append(decision)

    actions = {d.action for d in valid}
    # Only a decision recorded by the service confirms the list. The report's E4 field is outside the
    # report version and can be edited by hand, so it never confirms anything here.
    confirmed = 'confirm_requirements' in actions
    if not confirmed and (job.get('requirements_review') or {}).get('state') == 'confirmed':
        issues.append(Issue(code='report_confirmation_not_trusted'))
    taken: dict[str, set[str]] = {}
    for d in valid:
        if d.item_id is not None:
            taken.setdefault(d.item_id, set()).add(d.action)

    blockers, open_items, acknowledged, accepted = [], [], [], []
    for item in sorted(items.values(), key=lambda i: (i.priority, i.job_id or '', i.requirement_id or '',
                                                      i.condition_kind or '', i.reason_code, i.id)):
        need, done = CLOSED_BY.get(item.reason_code), taken.get(item.id, set())
        if item.reason_code in BLOCKERS:
            blockers.append(item.id)
            if done:  # a click never closes a blocker
                issues.append(Issue(code='blocker_not_closable', item_id=item.id))
            continue
        if done - {need}:
            issues.append(Issue(code='wrong_action', item_id=item.id))
        if need == 'confirm_requirements':
            (acknowledged if confirmed else open_items).append(item.id)
        elif need in done:
            (accepted if need == 'accept_condition' else acknowledged).append(item.id)
        else:
            open_items.append(item.id)

    marked = 'mark_for_handoff' in actions
    if not report.get('run_id'):  # without a run id, decisions of identical runs could not be told apart
        issues.append(Issue(code='run_unbound'))
    if any(i.code in {'not_a_service_decision', 'foreign_job', 'duplicate_decision'} for i in issues):
        state = 'invalid'
    elif blockers:
        state = 'blocked'
    elif marked and not open_items and report.get('run_id'):  # the list stays an item until confirmed
        state = 'reviewed_for_handoff'
    elif stale:
        state = 'stale'
    else:
        state = 'draft'
    if state == 'draft' and marked:
        issues.append(Issue(code='marked_with_open_items' if confirmed else 'marked_without_confirmed_list'))
    return HandoffAssessment(job_id=job_id, state=state, requirements_confirmed=confirmed,
                             processing_complete=processing_complete, blockers=blockers, open_items=open_items,
                             acknowledged=acknowledged, accepted_exceptions=accepted, reasons=issues)
