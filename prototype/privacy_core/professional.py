"""Bounded source grammar, not a global exemption for technology/company names.

Only exact public technical terms in explicit skill slots are candidates. A
finding must fit entirely inside one term; identities and structural detectors
always win. Employment/contractor language invalidates the whole slot. Derived
model data still uses unfiltered NER plus run-local source provenance.
"""
import re


# These are technical vocabulary, never exemptions in employer/name fields.
_TERMS = ('Vue.js', 'Vue', 'NoSQL', 'SQL', 'Git', 'TypeScript', 'JavaScript',
          'REST API', 'REST', 'GraphQL', 'Figma', 'Python', 'Java', 'HTML', 'CSS',
          'React', 'Node.js', 'PostgreSQL', 'MySQL', 'MongoDB', 'Redis', 'Docker',
          'Kubernetes', 'Excel', 'Power BI', 'CI/CD')
_TECH = re.compile(r'(?:' + '|'.join(re.escape(t) for t in sorted(_TERMS, key=len, reverse=True))
                   + r')(?!(?:[\w+-]|\.[\w]))', re.IGNORECASE)
_START = r'(?:^|(?<=[.!?]))[ \t]*(?:[-•*][ \t]+)?'
_SLOT = re.compile(
    _START + r'(?:не[ \t]+)?(?:опыт[ \t]+(?:коммерческой[ \t]+)?'
    r'(?:разработки[ \t]+на|работы[ \t]+с)|знани[ея]|'
    r'навыки[ \t]+(?:работы[ \t]+с|использования)|'
    r'работал[аи]?[ \t]+с|использовал[аи]?|разрабатывал[аи]?[ \t]+на|'
    r'понимание[ \t]+разницы[ \t]+между|(?:технологии|стек)[ \t]*:)'
    r'[ \t]+', re.IGNORECASE | re.MULTILINE)
_JOIN = re.compile(r'[ \t]*(?:,|/|\bи\b|\band\b)[ \t]*', re.IGNORECASE)
_END_CLAUSE = re.compile(r'[;\n]|[.!?](?=\s|$)')
_NEUTRAL_TAIL = re.compile(
    r'[ \t]*(?:\d{1,3}[ \t]+(?:год[а]?|лет|месяц(?:а|ев)?)[ \t]*)?'
    r'(?::[ \t]*компонентный подход(?:,[ \t]*(?:передача пропсов|работа с emit|v-model))*|'
    r'\(работа с макетом(?:,[ \t]*экспорт ресурсов)?\))?[ \t]*', re.IGNORECASE)
_RELATION = re.compile(
    r'\b(?:компани\w*|организаци\w*|работодател\w*|подрядчик\w*|'
    r'сотрудник\w*|поставщик\w*|клиент\w*|ооо|зао|пао|ип|'
    r'company|employer|contractor|employee|ltd|inc)\b|'
    r'\bгде[ \t]+работ|\bв[ \t]+котор\w*[ \t]+работ', re.IGNORECASE)
_EXPERIENCE = re.compile(
    _START + r'опыт[ \t]+работы(?:[ \t]*[:—–-]?[ \t]*'
    r'(?:\(?[ \t]*\d{1,3}[ \t]+(?:год[а]?|лет|месяц(?:а|ев)?)[ \t]*\)?)){0,2}'
    r'[ \t]*[:.]?[ \t]*$', re.IGNORECASE | re.MULTILINE)
_ROLE = re.compile(
    r'^[ \t]*(?:(?:Junior|Middle|Senior|Lead)[ \t]+)?'
    r'(?:Full[ -]Stack|Front[ -]?end|Back[ -]?end|Software|Data)[ \t]+'
    r'(?:Developer|Engineer|Analyst)[ \t]*$', re.IGNORECASE | re.MULTILINE)
_IDENTITY_LABEL = re.compile(r'(?:фио|ф\.?[ \t]*и\.?[ \t]*о\.?|имя|фамилия|name|full name)'
                             r'[ \t]*[:=—–-]?', re.IGNORECASE)
_STACK = re.compile(_START + r'(?:(?:основной|технологический|используемый)[ \t]+)?'
                    r'(?:стек|технологии|ключевые навыки)[ \t]*:[ \t]*(?:\n[ \t]*)?',
                    re.IGNORECASE | re.MULTILINE)
_USAGE = re.compile(
    r'\b(?:макет(?:а|ам|ами|ов|ы|е|ах)?[ \t]+(?:в[ \t]+)?(?P<design>Figma)|'
    r'интеграци(?:я|и|ю|ей|ями)[ \t]+(?:с[ \t]+)?(?P<api>REST API))'
    r'(?!(?:[\w+-]|\.[\w]))', re.IGNORECASE)


def _clause(text, start):
    end = _END_CLAUSE.search(text, start)
    return text[start:end.start() if end else len(text)]


def _clause_start(text, pos):
    # The match may occur in the second sentence on the same line.
    line = text.rfind('\n', 0, pos)+1
    for boundary in _END_CLAUSE.finditer(text, line, pos):
        line = boundary.end()
    return line


def source_spans(text):
    """Return exact professional spans and separately complete role headings."""
    roles = []
    for match in _ROLE.finditer(text):
        prefix = text[:match.start()].rstrip()
        previous = prefix[prefix.rfind('\n')+1:].strip()
        # A role-shaped value after an explicit identity label remains private,
        # including colon/newline/blank-line layouts missed by generic labels.
        if not _IDENTITY_LABEL.fullmatch(previous):
            roles.append(match.span())
    spans = list(roles)
    headings = list(roles)
    for match in _EXPERIENCE.finditer(text):
        # Keep only the common heading word eligible, not numbers or other text.
        word = re.search('опыт', match.group(), re.IGNORECASE)
        word_span = (match.start()+word.start(), match.start()+word.end())
        spans.append(word_span)
        headings.append(word_span)
    for slot in _SLOT.finditer(text):
        # Do not reinterpret an explicitly identified employer as a skill.
        clause = _clause(text, slot.start())
        if _RELATION.search(clause):
            continue
        terms, pos = [], slot.end()
        while term := _TECH.match(text, pos):
            terms.append(term.span())
            join = _JOIN.match(text, term.end())
            if not join:
                break
            pos = join.end()
        if terms:
            # A partial NER hit on "SQL" in "SQL Partners" is not a skill.
            # Require a complete recognized list and a neutral continuation.
            # Commas followed by arbitrary prose can identify an employer.
            last_end = terms[-1][1]
            if not _NEUTRAL_TAIL.fullmatch(_clause(text, last_end)):
                continue
            spans.extend(terms)
            word = re.search(r'\bопыт\b', slot.group(), re.IGNORECASE)
            if word:
                word_span = (slot.start()+word.start(), slot.start()+word.end())
                spans.append(word_span)
                headings.append(word_span)
    for stack in _STACK.finditer(text):
        # A stack list may contain unknown technical names. They are still
        # masked; they do not prevent an independently recognized next item.
        line = _clause(text, stack.end())
        if _RELATION.search(line):
            continue
        for item in re.finditer(r'[^,;]+', line):
            value = item.group().strip()
            term = _TECH.fullmatch(value)
            if term:
                start = stack.end()+item.start()+len(item.group())-len(item.group().lstrip())
                spans.append((start, start+len(value)))
    for usage in _USAGE.finditer(text):
        start = _clause_start(text, usage.start())
        if (not _RELATION.search(_clause(text, start))
                and _NEUTRAL_TAIL.fullmatch(_clause(text, usage.end()))):
            group = 'design' if usage.group('design') else 'api'
            spans.append(usage.span(group))
    return spans, roles, headings


def source_findings(text, findings):
    spans, roles, headings = source_spans(text)
    return [item for item in findings if not (
        item.method in {'ner', 'name_header'} and any(
            start <= item.start < item.end <= end
            for start, end in (roles if item.method == 'name_header' else
                               spans if item.kind == 'ORG' else
                               headings if item.kind == 'PERSON' else [])))]
