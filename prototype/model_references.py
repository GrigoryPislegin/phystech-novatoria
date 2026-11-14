"""Short, request-local aliases for already protected model payloads.

This table contains only opaque references, never their original values.
Durable sources/reports retain their original references and exact citations.
"""
import json
import re
import hashlib
import unicodedata

from .errors import ModelOutputError
from .privacy_core import REFERENCE


def _map_strings(value, transform):
    if isinstance(value, str):
        return transform(value)
    if isinstance(value, list):
        return [_map_strings(child, transform) for child in value]
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            key = transform(key)
            if key in result:
                raise ModelOutputError('model_invalid')
            result[key] = _map_strings(child, transform)
        return result
    return value


class ModelReferences:
    def __init__(self, checked_payload):
        source = json.dumps(checked_payload, ensure_ascii=False)
        normalized_source = unicodedata.normalize('NFKC', source).casefold()
        self.prefix = 'REF_'
        for attempt in range(8):
            if self.prefix[:-1].casefold() not in normalized_source:
                break
            suffix = hashlib.sha256((source + str(attempt)).encode()).hexdigest()[:8]
            self.prefix = 'REF' + suffix + '_'
        else:
            raise ModelOutputError('model_invalid')
        refs = dict.fromkeys(REFERENCE.findall(source))
        self.aliases = {ref:f'[[{self.prefix}{i}]]' for i, ref in enumerate(refs, 1)}
        self.originals = {alias:ref for ref, alias in self.aliases.items()}
        self.pattern = re.compile(r'\[\[' + re.escape(self.prefix) + r'\d+\]\]')

    def encode(self, value):
        return _map_strings(value, lambda text: REFERENCE.sub(lambda m:self.aliases[m[0]], text))

    def decode(self, value):
        def restore(text):
            def replace(match):
                if match[0] not in self.originals:
                    raise ModelOutputError('model_invalid')
                return self.originals[match[0]]
            text = self.pattern.sub(replace, text)
            # Unknown/changed aliases must not survive into a saved report.
            normalized = unicodedata.normalize('NFKC', text).casefold()
            bracketed = r'\[\s*\[?\s*' + re.escape(self.prefix[:-1].casefold())
            if self.prefix.casefold() in normalized or re.search(bracketed, normalized):
                raise ModelOutputError('model_invalid')
            return text
        return _map_strings(value, restore)
