"""Structural evidence checks bound to the processed text (E3).

Each quote is tied to its position, sentence and list heading in the processed text, and the
module reports whether that structure supports the model's row. Meaning is never confirmed:
a passing row is ``structure_ok`` with ``meaning='model_claim_unverified'``. ``needs_review``
is a check state, not a fifth match status, and the model status is kept as is. Technical
errors are ``invalid`` and never become ``unknown``.

Pure and local: no network, model calls or file writes. Not wired into pipeline/CLI yet,
see docs/reviews/egor-development-handoff.md.
"""
import bisect
import hashlib
import re
from functools import lru_cache
from typing import Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from .contracts import Evaluation, Facts, Requirement, Requirements, Row

INTEGRATED = False

# A sentence ends at .!?; only before whitespace or end of text: «Node.js», «ASP.NET», «3.5» stay whole.
_SENTENCE = re.compile(r'(?:[^\n.!?;]|[.!?;]+(?=[^\s.!?;]))+[.!?;]*')
_LIST_ITEM = re.compile(r'^\s*(?:[-*•–—]|\d+[.)])\s+\S')
_BULLET = re.compile(r'^[\s\-*•–—]+')
_CLOSING = re.compile(r'[\s.!?;,:]+$')
_WORD = re.compile(r'[0-9A-Za-zА-Яа-яЁё#+]+')

# Words that never link a requirement to evidence. A shared term does not prove relevance;
# its absence only sends the row to human review.
_GENERIC_WORDS = '''
    и или с со на в во по для от до не ни а но к о об у из за при как что это же
    лет года год годам месяцев мес менее более минимум
    опыт опыта опытом знание знания умение навыки навык владение уровень
    обязательно обязателен обязательна обязательны обязательное
    желательно желателен желательна желательны требуется требования требование плюсом будет
    работы работа работал работала разработки разрабатывал разработчик использовал использование писал писала
    and or with of in on the a an for to experience years year required preferred plus knowledge
'''.split()


def _stem(word: str) -> str:
    word = word.lower().replace('ё', 'е')
    return word[:5]


_GENERIC_STEMS = frozenset(map(_stem, _GENERIC_WORDS))


def _terms(text: str) -> set[str]:
    """Content stems; numbers, single non-Latin characters and generic words are dropped."""
    stems = set()
    for word in _WORD.findall(text):
        if word.isdigit() or (len(word) == 1 and not (word.isascii() and word.isalpha())):
            continue
        stem = _stem(word)
        if stem not in _GENERIC_STEMS:
            stems.add(stem)
    return stems


def core(text: str) -> str:
    """Text without list bullet and closing punctuation — the form quotes are compared in."""
    return _CLOSING.sub('', _BULLET.sub('', text))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def occurrences(text: str, quote: str) -> list[int]:
    """Start offsets of every (possibly overlapping) occurrence of a non-blank quote."""
    if not quote.strip():
        return []
    found, i = [], text.find(quote)
    while i != -1:
        found.append(i)
        i = text.find(quote, i + 1)
    return found


class Sentence(NamedTuple):
    start: int
    end: int
    text: str  # core form


class Heading(NamedTuple):
    start: int
    end: int
    block_end: int  # end of the list items directly under the heading
    text: str


class Layout(NamedTuple):
    sentences: tuple[Sentence, ...]
    starts: tuple[int, ...]
    headings: tuple[Heading, ...]


@lru_cache(maxsize=64)
def layout(text: str) -> Layout:
    """Sentences and list headings of a text, computed once per text.

    A heading is a line ending with ':' («Обязательно:»). Its block is only the list items
    directly under it and stops at a blank or non-list line («Желательно: SQL», «Будет плюсом»).
    """
    sentences = tuple(Sentence(m.start(), m.end(), core(m.group()))
                      for m in _SENTENCE.finditer(text) if core(m.group()))
    lines, pos = [], 0
    for line in text.split('\n'):
        lines.append((pos, pos + len(line), line))
        pos += len(line) + 1
    headings = []
    for i, (start, end, line) in enumerate(lines):
        if not line.strip().endswith(':'):
            continue
        block_end = end
        for _, item_end, item in lines[i + 1:]:
            if not _LIST_ITEM.match(item):
                break
            block_end = item_end
        headings.append(Heading(start, end, block_end, line.strip()))
    return Layout(sentences, tuple(s.start for s in sentences), tuple(headings))


def sentence_at(lay: Layout, start: int, end: int) -> Sentence | None:
    """The sentence that fully contains [start, end), or None if the span crosses sentences."""
    i = bisect.bisect_right(lay.starts, start) - 1
    if i >= 0 and end <= lay.sentences[i].end:
        return lay.sentences[i]
    return None


def context(lay: Layout, start: int, end: int) -> str:
    """The containing sentence, or every sentence the span touches joined with ' / '."""
    sentence = sentence_at(lay, start, end)
    if sentence:
        return sentence.text
    return ' / '.join(s.text for s in lay.sentences if s.start < end and start < s.end)


def heading_above(lay: Layout, start: int, end: int) -> Heading | None:
    for heading in lay.headings:
        if heading.end < start and end <= heading.block_end:
            return heading
    return None


class _Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Source(_Strict):
    source_id: str
    text: str
    sha256: str

    @classmethod
    def of(cls, source_id: str, text: str) -> 'Source':
        return cls(source_id=source_id, text=text, sha256=sha256_text(text))


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
    heading: str | None = None  # list heading above the quote, e.g. «Не работал с:»


class Located(_Strict):
    span: Span | None
    reason: Reason | None
    contexts: list[str] = Field(default_factory=list)


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


def _invalid(code: str, message: str, **extra) -> Reason:
    return Reason(code=code, severity='invalid', message=message, **extra)


def _review(code: str, message: str, **extra) -> Reason:
    return Reason(code=code, severity='review', message=message, **extra)


def locate(source: Source, quote: str, start: int | None = None) -> Located:
    """Find a quote in the processed text. Several different places are never resolved silently."""
    text = source.text
    if not quote.strip():
        return Located(span=None, reason=_invalid('empty_quote', 'Пустая цитата.'))
    if start is not None:
        if start < 0 or text[start:start + len(quote)] != quote:
            return Located(span=None, reason=_invalid('range_mismatch', 'Позиция не совпадает с цитатой в источнике.'))
        positions = [start]
    else:
        positions = occurrences(text, quote)
        if not positions:
            return Located(span=None, reason=_invalid('quote_not_found', 'Цитаты нет в источнике.'))
    lay = layout(text)
    contexts = list(dict.fromkeys(context(lay, p, p + len(quote)) for p in positions))
    if len(contexts) > 1:
        return Located(span=None, contexts=contexts, reason=_review(
            'ambiguous_location', 'Цитата встречается в разных местах; нужна позиция.', context=' | '.join(contexts)))
    pos, end = positions[0], positions[0] + len(quote)
    sentence, heading = sentence_at(lay, pos, end), heading_above(lay, pos, end)
    return Located(reason=None, contexts=contexts, span=Span(
        source_id=source.source_id, source_sha256=source.sha256, start=pos, end=end, quote=quote,
        sentence=sentence.text if sentence else None, heading=heading.text if heading else None))


def verify_span(span: Span, sources: dict[str, Source]) -> list[Reason]:
    """Re-check stored evidence against the processed source it claims to come from."""
    source = sources.get(span.source_id)
    if source is None:
        return [_invalid('unknown_source', 'Источник не найден.')]
    if source.sha256 != span.source_sha256:
        return [_invalid('source_mismatch', 'Источник изменился или не тот.')]
    if span.start < 0 or span.end - span.start != len(span.quote) or source.text[span.start:span.end] != span.quote:
        return [_invalid('range_mismatch', 'Диапазон не совпадает с цитатой.')]
    return []


def _row_shape(row: Row, requirement: Requirement) -> list[Reason]:
    reasons = []
    if row.requirement_id != requirement.id:
        reasons.append(_invalid('requirement_mismatch', 'Строка относится к другому требованию.'))
    if row.status == 'unknown' and row.fact_ids:
        reasons.append(_invalid('unknown_with_evidence', 'У статуса «не указано» не может быть доказательств.'))
    if row.status != 'unknown' and not row.fact_ids:
        reasons.append(_invalid('missing_evidence', 'Вывод без доказательства.'))
    if len(row.fact_ids) != len(set(row.fact_ids)):
        reasons.append(_invalid('duplicate_fact_id', 'Факт указан дважды.'))
    return reasons


def _evidence_reasons(span: Span, quote: str, requirement_terms: set[str], fact_id: str, lay: Layout) -> list[Reason]:
    if span.sentence is None:
        return [_review('quote_spans_sentences', 'Цитата захватывает несколько предложений.',
                        fact_id=fact_id, context=context(lay, span.start, span.end))]
    reasons = []
    if core(quote) != span.sentence:
        reasons.append(_review('quote_is_fragment', 'Цитата — часть предложения; проверьте предложение целиком.',
                               fact_id=fact_id, context=span.sentence))
    if not requirement_terms & _terms(span.sentence):
        reasons.append(_review('evidence_not_linked', 'В доказательстве нет ни одного термина требования.',
                               fact_id=fact_id, context=span.sentence))
    if span.heading:
        reasons.append(_review('heading_context', 'Пункт списка: смысл задаёт заголовок, проверьте его.',
                               fact_id=fact_id, context=f'{span.heading} → {span.sentence}'))
    return reasons


def check_row(row: Row, requirement: Requirement, facts: Facts, cv: Source) -> RowCheck:
    reasons, evidence = _row_shape(row, requirement), []
    by_id = {f.id: f for f in facts.items}
    requirement_terms = _terms(f'{requirement.text} {requirement.quote}')
    lay = layout(cv.text)
    for fact_id in row.fact_ids:
        fact = by_id.get(fact_id)
        if fact is None:
            reasons.append(_invalid('unknown_fact_id', 'Ссылка на несуществующий факт.', fact_id=fact_id))
            continue
        located = locate(cv, fact.quote)
        if located.reason:
            reasons.append(located.reason.model_copy(update={'fact_id': fact_id}))
            continue
        evidence.append(located.span)
        reasons += _evidence_reasons(located.span, fact.quote, requirement_terms, fact_id, lay)
    if any(r.severity == 'invalid' for r in reasons):
        state = 'invalid'
    elif reasons:
        state = 'needs_review'
    else:
        state = 'no_evidence' if row.status == 'unknown' else 'structure_ok'
    return RowCheck(requirement_id=row.requirement_id, status=row.status, state=state, reasons=reasons,
                    evidence=evidence)


def check_mandatory(requirement: Requirement, vacancy: Source) -> MandatoryCheck:
    """Is mandatory_quote tied to THIS requirement: same sentence, or a heading whose list holds it?"""
    rid, marker = requirement.id, requirement.mandatory_quote
    if marker is None:
        return MandatoryCheck(requirement_id=rid, state='not_mandatory', reasons=[])
    text, quote = vacancy.text, requirement.quote
    requirement_at, marker_at = occurrences(text, quote), occurrences(text, marker)
    if not requirement_at or not marker_at:
        what = 'требования' if not requirement_at else 'обязательности'
        return MandatoryCheck(requirement_id=rid, state='invalid',
                              reasons=[_invalid('quote_not_found', f'Цитаты {what} нет в вакансии.')])
    lay = layout(text)

    def governs(m: int, r: int) -> bool:
        m_end, r_end = m + len(marker), r + len(quote)
        sentence = sentence_at(lay, m, m_end)
        if sentence is None:  # a marker crossing sentences governs nothing
            return False
        if sentence.start <= r and r_end <= sentence.end:
            return True
        return any(h.start <= m and m_end <= h.end and h.end <= r and r_end <= h.block_end for h in lay.headings)

    linked = [r for r in requirement_at if any(governs(m, r) for m in marker_at)]
    if linked:
        places = {context(lay, r, r + len(quote)) for r in requirement_at}
        if len(linked) < len(requirement_at) and len(places) > 1:
            joined = ' | '.join(sorted(places))
            return MandatoryCheck(requirement_id=rid, state='needs_review', context=joined, reasons=[_review(
                'ambiguous_requirement_location',
                'Требование встречается в вакансии в разных местах; обязательность относится не ко всем.',
                context=joined)])
        return MandatoryCheck(requirement_id=rid, state='structure_ok', reasons=[],
                              context=context(lay, linked[0], linked[0] + len(quote)))
    joined = ' | '.join(context(lay, m, m + len(marker)) for m in marker_at)
    if any(sentence_at(lay, m, m + len(marker)) is None for m in marker_at):
        reason = _review('mandatory_spans_segments',
                         'Цитата обязательности захватывает несколько строк или предложений.', context=joined)
    else:
        reason = _review('mandatory_not_linked',
                         'Обязательность сказана в другом предложении или блоке, не у этого требования.',
                         context=joined)
    return MandatoryCheck(requirement_id=rid, state='needs_review', context=joined, reasons=[reason])


def check_pair(requirements: Requirements, facts: Facts, evaluation: Evaluation, cv: Source,
               vacancy: Source) -> PairCheck:
    by_id = {r.id: r for r in requirements.items}
    rows = [check_row(row, by_id[row.requirement_id], facts, cv) if row.requirement_id in by_id
            else RowCheck(requirement_id=row.requirement_id, status=row.status, state='invalid', evidence=[],
                          reasons=[_invalid('unknown_requirement_id', 'Строка без требования.')])
            for row in evaluation.rows]
    mandatory = [check_mandatory(r, vacancy) for r in requirements.items]
    states = {r.state for r in rows} | {m.state for m in mandatory}
    return PairCheck(cv_sha256=cv.sha256, vacancy_id=vacancy.source_id, vacancy_sha256=vacancy.sha256, rows=rows,
                     mandatory=mandatory, needs_review='needs_review' in states, has_invalid='invalid' in states)
