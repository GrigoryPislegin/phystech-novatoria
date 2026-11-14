"""Independent local pseudonymization with a run-local display map.

Russian NER + structural detectors. This is not proof of anonymity: contextual
identification, unsupported languages and detector misses require a human review.
"""
from dataclasses import dataclass
import asyncio
import hashlib
import hmac
import re
import secrets
import unicodedata
from collections import Counter
from ..errors import PrivacyError
from .professional import source_findings, source_spans

POLICY_VERSION = 'local-privacy-0.8'
REFERENCE = re.compile(r'\[\[PRIV:[a-f0-9]{16}:\d+:[A-Z]+\]\]')
RESERVED = '[[PRIV:'


@dataclass(frozen=True)
class Finding:
    start: int
    end: int
    kind: str
    method: str = 'rule'


# Capture only values after identifying labels; retain useful headings.
_LABELS = re.compile(
    r'(?im)(?:^|(?<=[;.!?]))[ \t]*(?:фио|ф\.?\s*и\.?\s*о\.?|имя|фамилия|full name|name|'
    r'дата рождения|год рождения|день рождения|родился|родилась|date of birth|dob|'
    r'паспорт|снилс|инн|passport)(?:[ \t]*[:=—–-][ \t]*|[ \t]*\n[ \t]*|[ \t]+)([^\s;:=—–-][^\n;]*)')
# Address fields may wrap across lines in an uploaded document. Continue only
# over explicit street/house fields; never swallow the next professional line.
# "Зарегистрирован патент" is an achievement, not an address declaration.
_RESIDENCE = re.compile(
    r'(?im)(?:^|(?<=[;.!?]))[ \t]*(?:[-•*—–][ \t]+)?'
    r'(?:(?:адрес(?: проживания)?|address|проживаю|проживает|место жительства|регистрация)'
    r'(?:[ \t]*[:=—–-][ \t]*|[ \t]*\n[ \t]*|[ \t]+)|'
    r'зарегистрирован(?:а)?(?:[ \t]*[:=—–-][ \t]*|[ \t]+по[ \t]+адресу[ \t]*:?[ \t]*))'
    r'(?:\r?\n[ \t]*)?([^\s;:=—–-][^\n;]*'
    r'(?:(?:\r?\n|;)[ \t]*(?:ул(?:ица)?|проспект|пр-т|переулок|пер|д(?:ом)?|'
    r'кв(?:артира)?|корпус|корп|строение|стр)[ .:]+[^\n;]*){0,3})')
_CONTACT_LABELS = re.compile(
    r'(?im)(?:^|(?<=[;.!?]))[ \t]*(?:telegram|телеграм|whatsapp|skype|linkedin|email|e-mail|сайт|website)'
    r'(?:[ \t]*[:=—–-][ \t]*|[ \t]*\n[ \t]*|[ \t]+)([^\s;:=—–-][^\s;]*)')
_PATTERNS = [
    ('EMAIL', re.compile(r'[\w.!#$%&\x27*+/=?^`{|}~−-]+\s*@\s*[\w-]+(?:\.[\w-]+)+', re.UNICODE)),
    ('EMAIL', re.compile(r'(?i)\b[\w.+-]+\s*(?:\[at\]|\(at\))\s*[\w.-]+\s*(?:\[dot\]|\(dot\)|\.)\s*\w+')),
    ('LINK', re.compile(r'(?i)(?:https?://|www\.|(?:t|vk)\.me/|vk\.com/|github\.com/|linkedin\.com/|hh\.ru/)[^\s<>]+')),
    ('LINK', re.compile(r'(?i)\b(?:[a-z0-9][a-z0-9-]*\.)+[a-z]{2,24}/[^\s<>]+')),
    ('LINK', re.compile(r'(?i)(?<![\w.-])(?:[^\W_][\w-]*\.)+(?:com|ru|org|net|io|dev|app|рф)(?![\w-]|\.[\w])')),
    ('HANDLE', re.compile(r'(?<!\w)@[\w.-]{2,}')),
    ('PHONE', re.compile(r'(?<!\w)(?:\+?\d[\s().-]*){10,15}(?!\w)')),
    ('DATE', re.compile(r'(?<!\d)\d{1,2}[./]\d{1,2}[./](?:19|20)\d{2}(?!\d)')),
    ('DATE', re.compile(r'(?<!\d)(?:19|20)\d{2}-\d{2}-\d{2}(?!\d)')),
    ('SECRET', re.compile(r'\bsk-[A-Za-z0-9_-]{16,}\b')),
]
# Russian news NER does not reliably recognize English name headers. This
# conservative structural rule may also hide title-case headings; no allowlist.
_NAME_LINE = re.compile(r'(?m)^\s*([A-Z][a-z]+(?:[-\x27][A-Z]?[a-z]+)?(?:[ \t]+[A-Z][a-z]+){1,3})[ \t]*$')
# News NER can miss an entire Russian CV name heading. Three capitalized
# name tokens including a patronymic give a bounded structural signal. Do not
# treat every capitalized professional heading as a personal name.
_RU_NAME_PART = r'(?:[А-ЯЁ][а-яё]{1,63}|[А-ЯЁ]{2,64})'
_NAME_DASHES = '-‐‑‒–—'
_RU_NAME_TOKEN = rf'{_RU_NAME_PART}(?:[{_NAME_DASHES}]{_RU_NAME_PART})?'
_RU_HEADER_PREFIX = r'[ \t]*(?:(?:[•*#–—-]|\d{1,2}[.)])[ \t]*)?'
_RU_HEADER_END = r'[ \t]*[.,;:]?[ \t]*\r?$'
_RU_NAME_LINE = re.compile(rf'(?m)^{_RU_HEADER_PREFIX}({_RU_NAME_TOKEN}(?:[ \t]+{_RU_NAME_TOKEN}){{2}}){_RU_HEADER_END}')
# Wrapped names are recognized only in the first heading, across at most two
# line breaks. Do not join arbitrary body paragraphs into a supposed identity.
_RU_NAME_HEADER = re.compile(rf'(?m)\A(?:[ \t]*\r?\n){{0,2}}{_RU_HEADER_PREFIX}'
                            rf'({_RU_NAME_TOKEN}(?:(?:[ \t]+|[ \t]*\r?\n[ \t]*){_RU_NAME_TOKEN}){{2}}){_RU_HEADER_END}')
# Bare "-ич" also matches professional words (кирпич, сэндвич). Short forms
# here are grammatical patronymics, not exceptions for professional entities.
_RU_PATRONYMIC = re.compile(r'(?:[а-яё]+(?:ович|евич|овна|евна|ична)|'
                           r'ильич|кузьмич|лукич|саввич|фомич|никитич)\Z', re.IGNORECASE)
# Explicit English self-identification, bounded to the name before punctuation.
# Do not consume the following professional sentence or treat arbitrary prose as a name.
_EN_NAME_TOKEN = r"(?:[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)*|[A-Z](?:[-'][A-Z][a-z]+)+|[A-Z]\.)"
_INTRODUCED_NAME = re.compile(
    rf"(?i:\bmy name is)[ \t]+({_EN_NAME_TOKEN}(?:[ \t]+{_EN_NAME_TOKEN}){{1,5}})"
    r"(?=[ \t]*(?:[.,;!?\r\n]|(?i:and\b)|$))")


class Detector:
    def __init__(self, ner):
        self.ner = ner

    def scan(self, text):
        found = []
        for kind, pattern in _PATTERNS:
            found.extend(Finding(m.start(), m.end(), kind) for m in pattern.finditer(text))
        found.extend(Finding(m.start(1), m.end(1), 'IDENTITY') for m in _LABELS.finditer(text))
        for match in _RESIDENCE.finditer(text):
            # Hide the field label together with its value. Otherwise a later
            # pass sees the blanked reference as whitespace after the label
            # and mistakes the next professional line for a wrapped address.
            # A new sentence after a numbered house ends the address field.
            ending = re.search(r'(?<=\d)\.[ \t]+(?=[А-ЯЁA-Z])', match[1])
            end = match.start(1)+ending.start() if ending else match.end(1)
            found.append(Finding(match.start(), end, 'LOCATION', 'residence'))
        found.extend(Finding(m.start(1), m.end(1), 'CONTACT') for m in _CONTACT_LABELS.finditer(text))
        found.extend(Finding(m.start(1), m.end(1), 'PERSON', 'name_header') for m in _NAME_LINE.finditer(text))
        found.extend(Finding(m.start(1), m.end(1), 'PERSON') for m in _RU_NAME_LINE.finditer(text)
                     if any(_RU_PATRONYMIC.fullmatch(token) for token in m.group(1).split()))
        header = _RU_NAME_HEADER.match(text)
        if header and '\n' in header.group(1) and any(_RU_PATRONYMIC.fullmatch(token) for token in header.group(1).split()):
            found.append(Finding(header.start(1), header.end(1), 'PERSON'))
        found.extend(Finding(m.start(1), m.end(1), 'PERSON') for m in _INTRODUCED_NAME.finditer(text))
        if not text.strip():
            return found
        # NER sees natural text; replacements are blanked by the caller.
        for span in self.ner(text).spans:
            if span.type not in {'PER', 'ORG', 'LOC'} or not 0 <= span.start < span.stop <= len(text):
                raise RuntimeError('privacy_detector_failed')
            found.append(Finding(span.start, span.stop, {'PER':'PERSON','ORG':'ORG','LOC':'LOCATION'}[span.type], 'ner'))
        return found


def _merge(findings, size):
    merged = []
    for item in sorted(findings, key=lambda s: (s.start, -s.end)):
        if not 0 <= item.start < item.end <= size:
            raise RuntimeError('privacy_detector_failed')
        if merged and item.start < merged[-1].end:
            prior = merged[-1]
            merged[-1] = Finding(prior.start, max(prior.end, item.end), prior.kind)
        else:
            merged.append(item)
    return merged


def normalized(text):
    # Both source quotes and findings use this same processed representation.
    return unicodedata.normalize('NFKC', ''.join(c for c in unicodedata.normalize('NFKC', text)
                                                if unicodedata.category(c) != 'Cf'))


def _canonical(text):
    return ' '.join(normalized(text).casefold().split())


class LocalPrivacy:
    """One instance per analysis; aliases are stable only within that run."""
    policy_version = POLICY_VERSION

    def __init__(self, detector):
        self.detector = detector
        self._key = secrets.token_bytes(32)
        self._nonce = secrets.token_hex(8)
        self._aliases = {}
        self._display_aliases = {}
        self.issued_refs = set()
        self.closed = False
        self.counts = {}
        self._hidden_lengths = set()
        self._hidden_values = set()
        self._safe_sources = []
        self._safe_roles = set()
        self._safe_professional_headers = set()
        self._contextual = Counter()

    def _ready(self):
        if self.closed:
            raise RuntimeError('privacy_closed')

    def _without_refs(self, text):
        def remove(match):
            if match.group() not in self.issued_refs:
                raise RuntimeError('privacy_untrusted_reference')
            return ' ' * len(match.group())
        clean = REFERENCE.sub(remove, text)
        if RESERVED in clean.upper():
            raise RuntimeError('privacy_untrusted_reference')
        return clean

    def _remember_hidden(self, text, finding):
        value = _canonical(text[finding.start:finding.end])
        values = {value}
        if finding.method == 'residence':
            field = _RESIDENCE.match(text[finding.start:finding.end])
            if field:
                address = field[1]
                values.add(_canonical(address))
                values.update(_canonical(part) for part in re.split(r'[,;\n]', address) if part.strip())
                for street in re.finditer(r'(?:^|[,;\n])[ \t]*(?:ул(?:ица)?|проспект|пр-т|переулок|пер)'
                                          r'[ .:]+([^,;\n]+)', address, re.IGNORECASE):
                    values.add(_canonical(street[1]))
        if finding.kind in {'PERSON','IDENTITY'}:
            # Labeled fields may swallow the rest of a sentence. Index the
            # identity before its first punctuation separately, not every word
            # of the swallowed professional prose. Unmerged NER findings below
            # additionally preserve shorter entities nested within that field.
            head = re.split(r'[,;.!?\n]', value, maxsplit=1)[0] if finding.kind == 'IDENTITY' else value
            tokens = re.findall(rf"[^\W\d_]+(?:[{_NAME_DASHES}'’][^\W\d_]+)*", head)[:4]
            values.update(token for token in tokens if len(token) >= 2)
            values.update(part for token in tokens for part in re.split(rf"[{_NAME_DASHES}'’]", token)
                          if len(part) >= 2)
            values.add(head)
        for hidden in values - {''}:
            self._hidden_lengths.add(len(hidden))
            self._hidden_values.add(hmac.digest(self._key, hidden.encode(), 'sha256'))

    def _mask(self, result, raw_findings):
        findings = _merge(raw_findings, len(result))
        references = list(REFERENCE.finditer(result))
        for item in raw_findings:
            self._remember_hidden(result, item)
        parts, pos = [], 0
        for item in findings:
            if any(item.start < ref.end() and ref.start() < item.end for ref in references):
                raise RuntimeError('privacy_residual_findings')
            self.counts[item.kind] = self.counts.get(item.kind, 0) + 1
            value = result[item.start:item.end]
            # Display references preserve exact spelling. The independent
            # hidden-value index still matches across case and spacing.
            digest = hmac.new(self._key, value.encode(), hashlib.sha256).digest()
            self._remember_hidden(result, item)
            if digest not in self._aliases:
                ref = f'[[PRIV:{self._nonce}:{len(self._aliases)+1}:{item.kind}]]'
                self._aliases[digest] = ref
                self._display_aliases[ref] = value
            ref = self._aliases[digest]
            self.issued_refs.add(ref)
            parts.extend((result[pos:item.start], ref))
            pos = item.end
        parts.append(result[pos:])
        return ''.join(parts)

    async def redact(self, text):
        self._ready()
        text = normalized(text)
        if RESERVED in text.upper():
            raise RuntimeError('privacy_untrusted_reference')
        result = text
        # Masking changes NER context: newly visible findings must also be hidden.
        # Bound the number of passes; non-convergence still blocks all model calls.
        for _ in range(3):
            clean = self._without_refs(result)
            raw_findings = source_findings(clean, self.detector.scan(clean))
            findings = _merge(raw_findings, len(result))
            if not findings:
                self._remember_source(clean)
                return result
            result = self._mask(result, raw_findings)
        await self.check(result)
        self._remember_source(self._without_refs(result))
        return result

    def _remember_source(self, text):
        self._safe_sources.append(text.casefold())
        self._safe_roles.update(_canonical(text[start:end]) for start, end in source_spans(text)[1])
        self._safe_professional_headers.update(_canonical(text[start:end]) for start, end in source_spans(text)[0])

    async def finalize_sources(self, sources):
        """Reconcile all protected sources against the final run-local index.

        A later document may identify a value missed in an earlier context.
        Rewrite sources before quotes/snapshots/model calls, never model quotes.
        """
        self._ready()
        self._safe_sources.clear()
        self._safe_roles.clear()
        self._safe_professional_headers.clear()
        sources = list(sources)
        # A hidden value can expose another NER span, which then propagates
        # to an earlier document on the next pass. Four passes were insufficient
        # for real 31-document batches; bound convergence by the batch size.
        for _ in range(max(4, min(64, 2*len(sources)))):
            changed = False
            for index, text in enumerate(sources):
                clean = self._without_refs(text)
                found = source_findings(clean, self.detector.scan(clean)) + await self._known_findings(clean, list(REFERENCE.finditer(text)))
                if found:
                    sources[index] = self._mask(text, found)
                    changed = True
            if not changed:
                for source in sources:
                    self._remember_source(self._without_refs(source))
                return sources
        raise PrivacyError('privacy_residual_findings')

    async def check(self, text):
        self._ready()
        text = self._without_refs(normalized(text))
        if source_findings(text, self.detector.scan(text)):
            raise RuntimeError('privacy_residual_findings')

    async def check_prepared_fields(self, values):
        # Keep JSON field boundaries: NER must not invent an organization from
        # the end of a quotation plus the next schema key ("Pinia. quote").
        fields, offset = [], 0
        values = [normalized(value) for value in values]
        for value in values:
            fields.append((offset, offset + len(value), value))
            offset += len(value) + 2
        await self.check_prepared('\n\n'.join(values), _fields=fields)

    async def check_prepared(self, text, *, _fields=()):
        """Check derived data without mutating quotes or globally exempting names.

        NER runs on every call. A contextual NER hit must occur verbatim in a
        fully scrubbed document from this session. Explicit identifiers and any
        previously hidden value still block, even when NER now misses them.
        Only successful source redaction grants provenance; responses never do.
        """
        self._ready()
        protected = normalized(text)
        text = self._without_refs(protected)
        blocked, contextual = Counter(), Counter()
        checked_fields = set()
        def professional_fragment(value):
            pattern = re.compile(r'(?<!\w)' + re.escape(_canonical(value)) + r'(?!\w)')
            return bool(value.strip()) and any(pattern.search(header)
                for header in self._safe_professional_headers)
        for item in self.detector.scan(text):
            if not 0 <= item.start < item.end <= len(text):
                raise RuntimeError('privacy_detector_failed')
            if item.method == 'ner' and item.kind == 'ORG' and _fields:
                touched = [(start, end, value) for start, end, value in _fields
                           if item.start < end and start < item.end]
                # Only a verified technical fragment plus the literal quote
                # field label can create this artificial organization. Names
                # split across values (Bill / Gates) must still be rejected.
                parts = [(text[max(start, item.start):min(end, item.end)].strip(' \t\r\n.,:;()'), field)
                         for start, end, field in touched]
                field_noise = (len(touched) > 1 and any(part == field == 'quote' for part, field in parts)
                    and all(part == field == 'quote' or professional_fragment(part) for part, field in parts))
                if field_noise:
                    # Recheck each whole field independently. Structural
                    # findings and the joined hidden-value scan below still
                    # apply; splitting a private value cannot exempt it.
                    for start, end, field in touched:
                        if start not in checked_fields:
                            await self.check_prepared(field)
                            checked_fields.add(start)
                    continue
            value = text[item.start:item.end].casefold()
            pattern = re.compile(r'(?<!\w)' + re.escape(value) + r'(?!\w)')
            can_inherit = (item.method == 'ner' or
                           (item.method == 'name_header' and professional_fragment(value)))
            if can_inherit and any(pattern.search(source) for source in self._safe_sources):
                contextual[item.kind] += 1
            else:
                blocked[item.kind] += 1
        known = await self._known_findings(text, list(REFERENCE.finditer(protected)))
        if known:
            blocked['KNOWN_VALUE'] = len(known)
        if blocked:
            raise PrivacyError('privacy_residual_findings', dict(blocked))
        self._contextual.update(contextual)

    async def _known_findings(self, text, references=()):
        # Canonical characters retain offsets into the normalized source. This
        # permits consistent masking without retaining original hidden values.
        chars, offsets, previous = [], [], 0
        for token in re.finditer(r'\S+', text):
            if chars:
                chars.append(' ')
                offsets.append((previous, token.start()))
            for i in range(token.start(), token.end()):
                for char in text[i].casefold():
                    chars.append(char)
                    offsets.append((i, i+1))
            previous = token.end()
        folded = ''.join(chars)
        found = []
        # Match at word boundaries, preserving short names without matching
        # syllables inside ordinary words. Yield for cancellation and bound work
        # before any SDK call; exceptionally dense inputs fail closed.
        attempts = 0
        starts = [i for i in range(len(folded)) if i == 0 or not (folded[i-1].isalnum() and folded[i].isalnum())]
        for size in sorted(self._hidden_lengths):
            for start in starts:
                end = start + size
                if end > len(folded):
                    break
                attempts += 1
                if attempts > 250_000:
                    raise PrivacyError('privacy_scan_limit')
                if attempts % 2048 == 0:
                    await asyncio.sleep(0)
                if end < len(folded) and folded[end-1].isalnum() and folded[end].isalnum():
                    continue
                value = folded[start:end]
                if value.isdecimal() and ((start >= 2 and folded[start-1] in './-' and folded[start-2].isdigit())
                                          or (end+1 < len(folded) and folded[end] in './-' and folded[end+1].isdigit())):
                    continue
                digest = hmac.digest(self._key, value.encode(), 'sha256')
                if digest in self._hidden_values:
                    left, right = offsets[start][0], offsets[end-1][1]
                    if not any(left < ref.end() and ref.start() < right for ref in references):
                        found.append(Finding(left, right, 'KNOWN'))
        return found

    def summary(self):
        return {'backend':POLICY_VERSION, 'kind':'pseudonymization_not_anonymity',
                'redactions':dict(self.counts),
                'contextual_findings':dict(self._contextual),
                'professional_information_may_be_hidden':bool(self.counts.get('ORG')),
                'requires_local_review':True}

    def export_display_aliases(self):
        self._ready()
        return self._display_aliases.copy()

    def close(self):
        # Best-effort lifetime control, not a claim of secure memory erasure.
        self._aliases.clear()
        self._display_aliases.clear()
        self.issued_refs.clear()
        self._hidden_lengths.clear()
        self._hidden_values.clear()
        self._safe_sources.clear()
        self._safe_roles.clear()
        self._safe_professional_headers.clear()
        self._key = b''
        self.closed = True
