"""Structural evidence checks bound to the processed text (E3).

Pure and local: no network, no model calls, no file writes. The module checks WHERE evidence
comes from and whether its structure supports the model's row; it never confirms meaning.
A row that passes is ``structure_ok`` with ``meaning='model_claim_unverified'``: still a model
claim until a human reviews it. ``needs_review`` is a check state, not a fifth match status;
the model status (full/partial/fail/unknown) is kept unchanged. Technical/validation errors are
``invalid`` and never turn into ``unknown``.

Not yet wired into pipeline/CLI: see docs/reviews/egor-development-handoff.md.
"""
import hashlib
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .contracts import Evaluation, Facts, Requirement, Requirements, Row

INTEGRATED = False

# A sentence ends at .!?; only before whitespace/end, so «Node.js», «ASP.NET», «3.5» stay whole.
_SEGMENT = re.compile(r'(?:[^\n.!?;]|[.!?;]+(?=[^\s.!?;]))+[.!?;]*')
_LIST_ITEM = re.compile(r'^\s*(?:[-*•–—]|\d+[.)])\s+\S')
_LEAD = re.compile(r'^[\s\-*•–—]+')
_TRAIL = re.compile(r'[\s.!?;,:]+$')
_TOKEN = re.compile(r'[0-9A-Za-zА-Яа-яЁё#+]+')

# Generic words never count as a link between a requirement and evidence. Their absence from
# this list can only send a row to review; a shared term never proves relevance.
_STOP_WORDS = '''и или с со на в во по для от до не ни а но к о об у из за при как что это же
лет года год годам месяцев мес менее более минимум опыт опыта опытом знание знания умение навыки навык
обязательно обязателен обязательна обязательны обязательное желательно желателен желательна желательны
требуется требования требование плюсом будет работы работа работал работала разработки разрабатывал
разработчик использовал использование писал писала владение уровень
and or with of in on the a an for to experience years year required preferred plus knowledge'''.split()


def _stem(token):
    token = token.lower().replace('ё', 'е')
    return token[:5] if len(token) > 5 else token


_STOP = {_stem(w) for w in _STOP_WORDS}


def _terms(text):
    out = set()
    for token in _TOKEN.findall(text):
        if token.isdigit():
            continue
        if len(token) == 1 and not re.match(r'[A-Za-z]', token):
            continue
        stem = _stem(token)
        if stem not in _STOP:
            out.add(stem)
    return out


def _norm(text):
    return _TRAIL.sub('', _LEAD.sub('', text))


class _Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Source(_Strict):
    source_id: str
    text: str
    sha256: str

    @classmethod
    def of(cls, source_id, text):
        return cls(source_id=source_id, text=text, sha256=hashlib.sha256(text.encode()).hexdigest())


class Reason(_Strict):
    code: str
    severity: Literal['invalid', 'review']
    message: str
    fact_id: str | None = None
    context: str | None = None


class Span(_Strict):
    source_id: str
    source_sha256: str
    start: int
    end: int
    quote: str
    sentence: str | None  # None when the quote crosses sentence boundaries
    heading: str | None = None  # list heading the quote sits under, e.g. «Не работал с:»


class Located(_Strict):
    span: Span | None
    reason: Reason | None
    contexts: list[str] = []


class RowCheck(_Strict):
    requirement_id: str
    status: Literal['full', 'partial', 'fail', 'unknown']
    state: Literal['structure_ok', 'needs_review', 'no_evidence', 'invalid']
    meaning: Literal['model_claim_unverified'] = 'model_claim_unverified'
    reasons: list[Reason]
    evidence: list[Span]


class MandatoryCheck(_Strict):
    requirement_id: str
    state: Literal['structure_ok', 'needs_review', 'not_mandatory', 'invalid']
    reasons: list[Reason]
    context: str | None = None


class PairCheck(_Strict):
    cv_sha256: str
    vacancy_id: str
    vacancy_sha256: str
    rows: list[RowCheck]
    mandatory: list[MandatoryCheck]
    needs_review: bool
    has_invalid: bool


def _segments(text):
    """(start, end, core) for each sentence/line; core has bullets and closing punctuation removed."""
    out = []
    for m in _SEGMENT.finditer(text):
        core = _norm(m.group())
        if core:
            out.append((m.start(), m.end(), core))
    return out


def _segment_of(segments, start, end):
    for seg_start, seg_end, core in segments:
        if seg_start <= start and end <= seg_end:
            return core
    return None


def _context(segments, start, end):
    """Sentence containing the span, or the joined sentences it touches."""
    one = _segment_of(segments, start, end)
    if one is not None:
        return one
    return ' / '.join(core for s, e, core in segments if s < end and start < e)


def _reason(code, severity, message, fact_id=None, context=None):
    return Reason(code=code, severity=severity, message=message, fact_id=fact_id, context=context)


def _occurrences(text, quote):
    found, i = [], text.find(quote)
    while i != -1:
        found.append(i)
        i = text.find(quote, i + 1)
    return found


def locate(source, quote, start=None):
    """Find the quote in the processed text. Never picks one of several different places silently."""
    text = source.text
    if not quote.strip():
        return Located(span=None, reason=_reason('empty_quote', 'invalid', 'Пустая цитата.'))
    segments = _segments(text)
    if start is not None:
        if start < 0 or start + len(quote) > len(text) or text[start:start + len(quote)] != quote:
            return Located(span=None, reason=_reason('range_mismatch', 'invalid',
                                                     'Позиция не совпадает с цитатой в источнике.'))
        positions = [start]
    else:
        positions = _occurrences(text, quote)
        if not positions:
            return Located(span=None, reason=_reason('quote_not_found', 'invalid', 'Цитаты нет в источнике.'))
    contexts = []
    for pos in positions:
        ctx = _context(segments, pos, pos + len(quote))
        if ctx not in contexts:
            contexts.append(ctx)
    if len(contexts) > 1:
        return Located(span=None, contexts=contexts,
                       reason=_reason('ambiguous_location', 'review',
                                      'Цитата встречается в разных местах; нужна позиция.',
                                      context=' | '.join(contexts)))
    pos = positions[0]
    return Located(span=Span(source_id=source.source_id, source_sha256=source.sha256, start=pos,
                             end=pos + len(quote), quote=quote,
                             sentence=_segment_of(segments, pos, pos + len(quote)),
                             heading=_heading_of(text, pos, pos + len(quote))),
                   reason=None, contexts=contexts)


def verify_span(span, sources):
    """Re-check stored evidence against the processed sources it claims to come from."""
    source = sources.get(span.source_id)
    if source is None:
        return [_reason('unknown_source', 'invalid', 'Источник не найден.')]
    if source.sha256 != span.source_sha256:
        return [_reason('source_mismatch', 'invalid', 'Источник изменился или не тот.')]
    if (span.start < 0 or span.end > len(source.text) or span.end - span.start != len(span.quote)
            or source.text[span.start:span.end] != span.quote):
        return [_reason('range_mismatch', 'invalid', 'Диапазон не совпадает с цитатой.')]
    return []


def check_row(row: Row, requirement: Requirement, facts: Facts, cv: Source) -> RowCheck:
    reasons, evidence = [], []
    if row.requirement_id != requirement.id:
        reasons.append(_reason('requirement_mismatch', 'invalid', 'Строка относится к другому требованию.'))
    if row.status == 'unknown' and row.fact_ids:
        reasons.append(_reason('unknown_with_evidence', 'invalid', 'У статуса «не указано» не может быть доказательств.'))
    if row.status != 'unknown' and not row.fact_ids:
        reasons.append(_reason('missing_evidence', 'invalid', 'Вывод без доказательства.'))
    if len(row.fact_ids) != len(set(row.fact_ids)):
        reasons.append(_reason('duplicate_fact_id', 'invalid', 'Факт указан дважды.'))
    by_id = {f.id: f for f in facts.items}
    requirement_terms = _terms(f'{requirement.text} {requirement.quote}')
    for fact_id in row.fact_ids:
        fact = by_id.get(fact_id)
        if fact is None:
            reasons.append(_reason('unknown_fact_id', 'invalid', 'Ссылка на несуществующий факт.', fact_id))
            continue
        located = locate(cv, fact.quote)
        if located.reason:
            reasons.append(located.reason.model_copy(update={'fact_id': fact_id}))
            continue
        span = located.span
        evidence.append(span)
        segments = _segments(cv.text)
        if span.sentence is None:
            reasons.append(_reason('quote_spans_sentences', 'review', 'Цитата захватывает несколько предложений.',
                                   fact_id, _context(segments, span.start, span.end)))
            continue
        if _norm(fact.quote) != span.sentence:
            reasons.append(_reason('quote_is_fragment', 'review',
                                   'Цитата — часть предложения; проверьте предложение целиком.', fact_id, span.sentence))
        if not requirement_terms & _terms(span.sentence):
            reasons.append(_reason('evidence_not_linked', 'review',
                                   'В доказательстве нет ни одного термина требования; связь не показана.',
                                   fact_id, span.sentence))
        if span.heading:
            reasons.append(_reason('heading_context', 'review',
                                   'Пункт списка: смысл задаёт заголовок, проверьте его.', fact_id,
                                   f'{span.heading} → {span.sentence}'))
    if any(r.severity == 'invalid' for r in reasons):
        state = 'invalid'
    elif reasons:
        state = 'needs_review'
    elif row.status == 'unknown':
        state = 'no_evidence'
    else:
        state = 'structure_ok'
    return RowCheck(requirement_id=row.requirement_id, status=row.status, state=state, reasons=reasons,
                    evidence=evidence)


def _heading_blocks(text):
    """(line_start, line_end, block_end) for lines ending with ':' — e.g. «Обязательно:».

    The block is only the list items directly under the heading; it ends at the first blank or
    non-list line («Желательно: SQL», «Будет плюсом»), so an unlisted line is never pulled in.
    """
    lines, pos = [], 0
    for line in text.split('\n'):
        lines.append((pos, pos + len(line), line))
        pos += len(line) + 1
    blocks = []
    for i, (start, end, line) in enumerate(lines):
        if not line.strip().endswith(':'):
            continue
        block_end = end
        for item_start, item_end, item in lines[i + 1:]:
            if not _LIST_ITEM.match(item):
                break
            block_end = item_end
        blocks.append((start, end, block_end))
    return blocks


def _heading_of(text, start, end):
    for line_start, line_end, block_end in _heading_blocks(text):
        if line_end < start and end <= block_end:
            return text[line_start:line_end].strip()
    return None


def check_mandatory(requirement: Requirement, vacancy: Source) -> MandatoryCheck:
    """Is mandatory_quote structurally tied to THIS requirement (same sentence or heading block)?"""
    rid = requirement.id
    if requirement.mandatory_quote is None:
        return MandatoryCheck(requirement_id=rid, state='not_mandatory', reasons=[])
    text, quote = vacancy.text, requirement.mandatory_quote
    req_positions = _occurrences(text, requirement.quote)
    mand_positions = _occurrences(text, quote) if quote.strip() else []
    if not req_positions or not mand_positions:
        what = 'требования' if not req_positions else 'обязательности'
        return MandatoryCheck(requirement_id=rid, state='invalid',
                              reasons=[_reason('quote_not_found', 'invalid', f'Цитаты {what} нет в вакансии.')])
    segments, heads = _segments(text), _heading_blocks(text)
    crosses, contexts, linked_at = False, [], {}
    for m in mand_positions:
        m_end = m + len(quote)
        seg = None
        for s, e, core in segments:
            if s <= m and m_end <= e:
                seg = (s, e, core)
        contexts.append(_context(segments, m, m_end))
        if seg is None:
            crosses = True
            continue
        for r in req_positions:
            r_end = r + len(requirement.quote)
            same_sentence = seg[0] <= r and r_end <= seg[1]
            under_heading = any(line_start <= m and m_end <= line_end and line_end <= r and r_end <= block_end
                                for line_start, line_end, block_end in heads)
            if same_sentence or under_heading:
                linked_at.setdefault(r, seg[2])
    if linked_at:
        req_contexts = {_context(segments, r, r + len(requirement.quote)) for r in req_positions}
        if len(req_contexts) > 1 and len(linked_at) < len(req_positions):
            joined = ' | '.join(sorted(req_contexts))
            return MandatoryCheck(requirement_id=rid, state='needs_review', context=joined, reasons=[
                _reason('ambiguous_requirement_location', 'review',
                        'Требование встречается в вакансии в разных местах; обязательность относится не ко всем.',
                        context=joined)])
        return MandatoryCheck(requirement_id=rid, state='structure_ok', reasons=[],
                              context=next(iter(linked_at.values())))
    context = ' | '.join(contexts)
    if crosses:
        return MandatoryCheck(requirement_id=rid, state='needs_review', context=context, reasons=[
            _reason('mandatory_spans_segments', 'review',
                    'Цитата обязательности захватывает несколько строк или предложений.', context=context)])
    return MandatoryCheck(requirement_id=rid, state='needs_review', context=context, reasons=[
        _reason('mandatory_not_linked', 'review',
                'Обязательность сказана в другом предложении или блоке, не у этого требования.', context=context)])


def check_pair(requirements: Requirements, facts: Facts, evaluation: Evaluation, cv: Source,
               vacancy: Source) -> PairCheck:
    by_id = {r.id: r for r in requirements.items}
    rows = []
    for row in evaluation.rows:
        requirement = by_id.get(row.requirement_id)
        if requirement is None:
            rows.append(RowCheck(requirement_id=row.requirement_id, status=row.status, state='invalid', evidence=[],
                                 reasons=[_reason('unknown_requirement_id', 'invalid', 'Строка без требования.')]))
        else:
            rows.append(check_row(row, requirement, facts, cv))
    mandatory = [check_mandatory(r, vacancy) for r in requirements.items]
    states = [r.state for r in rows] + [m.state for m in mandatory]
    return PairCheck(cv_sha256=cv.sha256, vacancy_id=vacancy.source_id, vacancy_sha256=vacancy.sha256, rows=rows,
                     mandatory=mandatory, needs_review='needs_review' in states, has_invalid='invalid' in states)
