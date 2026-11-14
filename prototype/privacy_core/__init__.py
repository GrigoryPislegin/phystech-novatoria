"""Independent local pseudonymization. No certum_core, database or restoration API.

Russian NER + structural detectors. This is not proof of anonymity: contextual
identification, unsupported languages and detector misses require a human review.
"""
from dataclasses import dataclass
import hashlib
import hmac
import re
import secrets
import unicodedata

POLICY_VERSION = 'local-privacy-0.3'
REFERENCE = re.compile(r'\[\[PRIV:[a-f0-9]{16}:\d+:[A-Z]+\]\]')
RESERVED = '[[PRIV:'


@dataclass(frozen=True)
class Finding:
    start: int
    end: int
    kind: str


# Capture only values after identifying labels; retain useful headings.
_LABELS = re.compile(
    r'(?im)(?:^|(?<=[;.!?]))[ \t]*(?:фио|ф\.?\s*и\.?\s*о\.?|имя|фамилия|full name|name|'
    r'адрес(?: проживания)?|address|дата рождения|год рождения|день рождения|родился|родилась|date of birth|dob|'
    r'паспорт|снилс|инн|passport)(?:[ \t]*[:=—–-][ \t]*|[ \t]*\n[ \t]*|[ \t]+)([^\s;:=—–-][^\n;]*)')
_CONTACT_LABELS = re.compile(
    r'(?im)(?:^|(?<=[;.!?]))[ \t]*(?:telegram|телеграм|whatsapp|skype|linkedin|email|e-mail|сайт|website)'
    r'(?:[ \t]*[:=—–-][ \t]*|[ \t]*\n[ \t]*|[ \t]+)([^\s;:=—–-][^\s;]*)')
_PATTERNS = [
    ('EMAIL', re.compile(r'[\w.!#$%&\x27*+/=?^`{|}~−-]+\s*@\s*[\w-]+(?:\.[\w-]+)+', re.UNICODE)),
    ('EMAIL', re.compile(r'(?i)\b[\w.+-]+\s*(?:\[at\]|\(at\))\s*[\w.-]+\s*(?:\[dot\]|\(dot\)|\.)\s*\w+')),
    ('LINK', re.compile(r'(?i)(?:https?://|www\.|(?:t|vk)\.me/|vk\.com/|github\.com/|linkedin\.com/|hh\.ru/)[^\s<>]+')),
    ('LINK', re.compile(r'(?i)\b(?:[a-z0-9][a-z0-9-]*\.)+[a-z]{2,24}/[^\s<>]+')),
    ('HANDLE', re.compile(r'(?<!\w)@[\w.-]{2,}')),
    ('PHONE', re.compile(r'(?<!\w)(?:\+?\d[\s().-]*){10,15}(?!\w)')),
    ('DATE', re.compile(r'(?<!\d)\d{1,2}[./]\d{1,2}[./](?:19|20)\d{2}(?!\d)')),
    ('DATE', re.compile(r'(?<!\d)(?:19|20)\d{2}-\d{2}-\d{2}(?!\d)')),
    ('SECRET', re.compile(r'\bsk-[A-Za-z0-9_-]{16,}\b')),
]
# Russian news NER does not reliably recognize English name headers. This
# conservative structural rule may also hide title-case headings; no allowlist.
_NAME_LINE = re.compile(r'(?m)^\s*([A-Z][a-z]+(?:[-\x27][A-Z]?[a-z]+)?(?:[ \t]+[A-Z][a-z]+){1,3})[ \t]*$')
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
        found.extend(Finding(m.start(1), m.end(1), 'CONTACT') for m in _CONTACT_LABELS.finditer(text))
        found.extend(Finding(m.start(1), m.end(1), 'PERSON') for m in _NAME_LINE.finditer(text))
        found.extend(Finding(m.start(1), m.end(1), 'PERSON') for m in _INTRODUCED_NAME.finditer(text))
        if not text.strip():
            return found
        # NER sees natural text; replacements are blanked by the caller.
        for span in self.ner(text).spans:
            if span.type not in {'PER', 'ORG', 'LOC'} or not 0 <= span.start < span.stop <= len(text):
                raise RuntimeError('privacy_detector_failed')
            found.append(Finding(span.start, span.stop, {'PER':'PERSON','ORG':'ORG','LOC':'LOCATION'}[span.type]))
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
    return ''.join(c for c in unicodedata.normalize('NFKC', text) if unicodedata.category(c) != 'Cf')


class LocalPrivacy:
    """One instance per analysis; aliases are stable only within that run."""
    policy_version = POLICY_VERSION

    def __init__(self, detector):
        self.detector = detector
        self._key = secrets.token_bytes(32)
        self._nonce = secrets.token_hex(8)
        self._aliases = {}
        self.issued_refs = set()
        self.closed = False
        self.counts = {}

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
            findings = _merge(self.detector.scan(clean), len(result))
            if not findings:
                return result
            references = list(REFERENCE.finditer(result))
            parts, pos = [], 0
            for item in findings:
                if any(item.start < ref.end() and ref.start() < item.end for ref in references):
                    raise RuntimeError('privacy_residual_findings')
                self.counts[item.kind] = self.counts.get(item.kind, 0) + 1
                value = result[item.start:item.end]
                digest = hmac.new(self._key, value.casefold().encode(), hashlib.sha256).digest()
                if digest not in self._aliases:
                    self._aliases[digest] = f'[[PRIV:{self._nonce}:{len(self._aliases)+1}:{item.kind}]]'
                ref = self._aliases[digest]
                self.issued_refs.add(ref)
                parts.extend((result[pos:item.start], ref))
                pos = item.end
            parts.append(result[pos:])
            result = ''.join(parts)
        await self.check(result)
        return result

    async def check(self, text):
        self._ready()
        text = self._without_refs(normalized(text))
        if self.detector.scan(text):
            raise RuntimeError('privacy_residual_findings')

    def summary(self):
        return {'backend':POLICY_VERSION, 'kind':'pseudonymization_not_anonymity',
                'redactions':dict(self.counts),
                'professional_information_may_be_hidden':bool(self.counts.get('ORG')),
                'requires_local_review':True}

    def close(self):
        # Best-effort lifetime control, not a claim of secure memory erasure.
        self._aliases.clear()
        self.issued_refs.clear()
        self._key = b''
        self.closed = True
