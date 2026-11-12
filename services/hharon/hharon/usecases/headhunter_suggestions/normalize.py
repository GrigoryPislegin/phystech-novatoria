import transliterate  # type: ignore[import-untyped]  # ty: ignore[unused-ignore-comment]

from hharon.usecases.headhunter_suggestions.constants import (
    CITIZENSHIP_PREFIXES,
    EDUCATIONAL_SUFFIXES,
    METRO_SUFFIXES,
)
from hharon_api.v1 import hharon_pb2


def normalize_for_filter(text: str) -> str:
    """Normalize string for filtering: collapse spaces, lowercase."""
    return " ".join(text.strip().split()).lower()


def _transliterate_text(text: str) -> str:
    try:
        return str(transliterate.translit(text, "ru", reversed=True)).lower()  # pyright: ignore[reportUnknownArgumentType]
    except Exception:
        return text.lower()


def _strip_tails(s: str, tails: tuple[str, ...]) -> str:
    for tail in tails:
        if s.endswith(tail):
            return s[: -len(tail)].rstrip()
    return s


def _strip_prefixes(s: str, prefixes: tuple[str, ...]) -> str:
    for pref in prefixes:
        if s.startswith(pref):
            return s[len(pref) :].lstrip()
    return s


def _strip_field_noise(field: hharon_pb2.GetHeadhunterSuggestionsRequest.Field.ValueType, s: str) -> str:
    if field == hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_METRO:
        return _strip_tails(s, METRO_SUFFIXES)
    if field == hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_CITIZENSHIP:
        return _strip_prefixes(s, CITIZENSHIP_PREFIXES)
    if field == hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_EDUCATIONAL_INSTITUTION:
        return _strip_tails(s, EDUCATIONAL_SUFFIXES)
    return s


def _has_cyrillic(s: str) -> bool:
    return any("\u0400" <= c <= "\u04ff" for c in s)


def normalize_for_matching(field: hharon_pb2.GetHeadhunterSuggestionsRequest.Field.ValueType, text: str) -> str:
    if not text:
        return ""
    s = normalize_for_filter(text)
    s = _strip_field_noise(field, s)
    if field == hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL and _has_cyrillic(s):
        s = _transliterate_text(s)
    return s
