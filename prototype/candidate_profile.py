"""Short professional profile and CV↔vacancy conditions (E5): schemas and structural checks.

The model fills the schemas; the checks bind every claim to the processed CV:
- each claim cites a fact id and an exact fragment of that fact's quote;
- a digit in a claim must appear in its sources; numbers in words and other paraphrase are not checked,
  so the report shows the claim text only when it is inside a quote (`display`);
- an empty section is listed in `missing`, never filled in;
- the last position needs a period with a year from the same fact as the role;
  a later year anywhere in the CV sends it to review.
The DTO has no personal fields: no name, contacts, age or employer.

Conditions are compared only when both documents state them; otherwise the state is `unknown`.
A conflict is highlighted for the recruiter. It never rejects the candidate or changes the score.
Salary comparisons always go to review: currency, period and gross/net are not compared here.

Passing checks mean the structure holds; the meaning stays a model claim.
Pure and local. Wired into pipeline and local service; see docs/28-local-app-runbook.md.
"""
import re
from typing import Literal

from pydantic import Field

from .contracts import Facts, StrictModel
from .evidence import Located, Source, Span, locate

INTEGRATED = True
SCHEMA_VERSION = 'candidate-profile-0.1'

Section = Literal['summary', 'stack', 'last_position', 'achievements']
ConditionKind = Literal['work_mode', 'location', 'schedule', 'relocation', 'salary']
CheckState = Literal['structure_ok', 'needs_review', 'invalid']

_NUMBER = re.compile(r'\d+(?:[.,]\d+)?')
_DIGIT_GROUP = re.compile(r'(?<=\d)[\s ](?=\d{3}\b)')
# A year is a 4-digit 19xx/20xx not followed by a word other than «г.»/«года»: «2000 пользователей» is a count.
_YEAR = re.compile(r'(?<!\d)(?:19|20)\d{2}(?!\d)(?!\s*(?![гГ])[A-Za-zА-Яа-яЁё])')


# --- Model output ---------------------------------------------------------------------------

class ClaimSource(StrictModel):
    fact_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)  # exact fragment of that fact's quote


class Claim(StrictModel):
    text: str = Field(min_length=1)  # model paraphrase; the UI shows it only if it is inside a quote
    sources: list[ClaimSource] = Field(min_length=1, max_length=5)


class LastPosition(StrictModel):
    role: Claim
    domain: Claim | None
    period: Claim  # must quote dates; without them last_position is null


class Achievement(StrictModel):
    action: Claim
    result: Claim | None  # only an outcome stated in the CV


class CandidateProfile(StrictModel):
    summary: list[Claim] = Field(max_length=3)
    stack: list[Claim] = Field(max_length=30)
    last_position: LastPosition | None
    achievements: list[Achievement] = Field(max_length=5)
    missing: list[Section]


class ConditionComparison(StrictModel):
    kind: ConditionKind
    state: Literal['compatible', 'conflict', 'unknown']
    cv: ClaimSource | None
    vacancy_quote: str | None
    note: str = Field(min_length=1)  # model explanation, unverified


class Conditions(StrictModel):
    items: list[ConditionComparison] = Field(max_length=10)


# --- Check results --------------------------------------------------------------------------

class Finding(StrictModel):
    where: str  # path in the DTO, e.g. 'achievements[0].result'
    code: str
    severity: Literal['invalid', 'review']
    message: str
    context: str | None = None


class ProfileCheck(StrictModel):
    schema_version: Literal['candidate-profile-0.1'] = SCHEMA_VERSION
    state: CheckState
    meaning: Literal['model_claim_unverified'] = 'model_claim_unverified'
    findings: list[Finding]
    spans: dict[str, list[Span]]  # claim path -> located CV fragments
    display: dict[str, str]  # claim path -> what the report shows: the text if inside a quote, else the quotes


class ConditionCheck(StrictModel):
    kind: ConditionKind
    state: Literal['compatible', 'conflict', 'unknown']  # as proposed by the model
    check: CheckState
    findings: list[Finding]
    cv_span: Span | None
    vacancy_span: Span | None


class ConditionsCheck(StrictModel):
    items: list[ConditionCheck]
    findings: list[Finding]  # list-level problems
    conflicts: list[ConditionKind]
    needs_review: bool
    has_invalid: bool


def _invalid(where: str, code: str, message: str, context: str | None = None) -> Finding:
    return Finding(where=where, code=code, severity='invalid', message=message, context=context)


def _review(where: str, code: str, message: str, context: str | None = None) -> Finding:
    return Finding(where=where, code=code, severity='review', message=message, context=context)


def _state(findings: list[Finding]) -> CheckState:
    severities = {f.severity for f in findings}
    return 'invalid' if 'invalid' in severities else 'needs_review' if severities else 'structure_ok'


def _numbers(text: str) -> set[str]:
    return {n.replace(',', '.') for n in _NUMBER.findall(_DIGIT_GROUP.sub('', text))}


def _from_located(where: str, located: Located) -> Finding:
    reason = located.reason
    return Finding(where=where, code=reason.code, severity=reason.severity, message=reason.message,
                   context=reason.context)


def _locate_source(where: str, source: ClaimSource, facts: Facts, cv: Source) -> tuple[Span | None, list[Finding]]:
    """Place a cited fragment inside its fact, then inside the CV."""
    fact = next((f for f in facts.items if f.id == source.fact_id), None)
    if fact is None:
        return None, [_invalid(where, 'unknown_fact_id', 'Факта с таким id нет.')]
    offset = fact.quote.find(source.quote)
    if not source.quote.strip() or offset < 0:
        return None, [_invalid(where, 'quote_not_in_fact', 'Цитаты нет в цитате факта.')]
    fact_at = locate(cv, fact.quote)
    if fact_at.span is None:
        return None, [_from_located(where, fact_at)]
    span = locate(cv, source.quote, fact_at.span.start + offset).span
    return span, []


def _check_claim(where: str, claim: Claim, facts: Facts, cv: Source,
                 spans: dict[str, list[Span]]) -> list[Finding]:
    findings, located = [], []
    for i, source in enumerate(claim.sources):
        span, problems = _locate_source(f'{where}.sources[{i}]', source, facts, cv)
        findings += problems
        if span is not None:
            located.append(span)
    spans[where] = located
    quoted = set().union(*(_numbers(s.quote) for s in claim.sources))
    invented = sorted(_numbers(claim.text) - quoted)
    if invented:
        findings.append(_invalid(where, 'number_not_in_source',
                                 'В утверждении есть число, которого нет в цитатах: ' + ', '.join(invented)))
    return findings


def _claims(profile: CandidateProfile):
    for i, claim in enumerate(profile.summary):
        yield f'summary[{i}]', claim
    for i, claim in enumerate(profile.stack):
        yield f'stack[{i}]', claim
    if profile.last_position is not None:
        for field in ('role', 'domain', 'period'):
            claim = getattr(profile.last_position, field)
            if claim is not None:
                yield f'last_position.{field}', claim
    for i, achievement in enumerate(profile.achievements):
        yield f'achievements[{i}].action', achievement.action
        if achievement.result is not None:
            yield f'achievements[{i}].result', achievement.result


def _years(text: str) -> set[int]:
    return {int(y) for y in _YEAR.findall(text)}


def check_profile(profile: CandidateProfile, facts: Facts, cv: Source) -> ProfileCheck:
    findings: list[Finding] = []
    spans: dict[str, list[Span]] = {}
    display: dict[str, str] = {}
    for where, claim in _claims(profile):
        findings += _check_claim(where, claim, facts, cv, spans)
        quotes = [s.quote for s in claim.sources]
        display[where] = claim.text if any(claim.text in q for q in quotes) else ' / '.join(quotes)

    present = {'summary': bool(profile.summary), 'stack': bool(profile.stack),
               'last_position': profile.last_position is not None, 'achievements': bool(profile.achievements)}
    if len(profile.missing) != len(set(profile.missing)):
        findings.append(_invalid('missing', 'duplicate_section', 'Раздел указан в missing дважды.'))
    for section, filled in present.items():
        if filled == (section in profile.missing):
            findings.append(_invalid(section, 'missing_mismatch',
                                     'Раздел должен быть либо заполнен, либо указан в missing.'))

    if profile.last_position is not None:
        position = profile.last_position
        period_years = set().union(*(_years(s.quote) for s in position.period.sources))
        if not {s.fact_id for s in position.period.sources} & {s.fact_id for s in position.role.sources}:
            findings.append(_invalid('last_position.period', 'period_not_bound_to_role',
                                     'Период взят не из того факта, что роль; даты нельзя заимствовать.'))
        if not period_years:
            findings.append(_invalid('last_position.period', 'undated_last_position',
                                     'Последнее место без дат в цитате; его нельзя вычислить.'))
        else:
            later = sorted(y for y in _years(cv.text) if y > max(period_years))
            if later:
                message = f'В резюме есть более поздний год ({later[-1]}); проверьте, что место последнее.'
                findings.append(_review('last_position.period', 'later_period_in_cv', message))
    return ProfileCheck(state=_state(findings), findings=findings, spans=spans, display=display)


def check_conditions(conditions: Conditions, facts: Facts, cv: Source, vacancy: Source) -> ConditionsCheck:
    list_findings = []
    kinds = [c.kind for c in conditions.items]
    for kind in sorted({k for k in kinds if kinds.count(k) > 1}):
        list_findings.append(_invalid('conditions', 'duplicate_kind', f'Условие {kind} указано дважды.'))

    items = []
    for i, item in enumerate(conditions.items):
        where, findings = f'conditions[{i}]', []
        cv_span = vacancy_span = None
        if item.cv is not None:
            cv_span, problems = _locate_source(f'{where}.cv', item.cv, facts, cv)
            findings += problems
        if item.vacancy_quote is not None:
            located = locate(vacancy, item.vacancy_quote)
            vacancy_span = located.span
            if located.span is None:
                findings.append(_from_located(f'{where}.vacancy_quote', located))
        if item.state != 'unknown' and (item.cv is None or item.vacancy_quote is None):
            findings.append(_invalid(where, 'one_sided_comparison',
                                     'Совместимость и конфликт требуют цитат из обоих документов.'))
        if item.state == 'unknown' and item.cv is not None and item.vacancy_quote is not None:
            findings.append(_review(where, 'unknown_with_both_sides',
                                    'Обе стороны указаны, но сравнение не сделано; сравните вручную.'))
        if item.kind == 'salary' and item.state != 'unknown':
            findings.append(_review(where, 'salary_terms_unverified',
                                    'Валюта, период и налог автоматически не сравниваются.'))
        if item.state == 'conflict':
            findings.append(_review(where, 'condition_conflict',
                                    'Показать HR. Конфликт условий не является автоматическим отказом.'))
        items.append(ConditionCheck(kind=item.kind, state=item.state, check=_state(findings), findings=findings,
                                    cv_span=cv_span, vacancy_span=vacancy_span))

    every = list_findings + [f for c in items for f in c.findings]
    return ConditionsCheck(items=items, findings=list_findings,
                           conflicts=[c.kind for c in items if c.state == 'conflict'],
                           needs_review=any(f.severity == 'review' for f in every),
                           has_invalid=any(f.severity == 'invalid' for f in every))
