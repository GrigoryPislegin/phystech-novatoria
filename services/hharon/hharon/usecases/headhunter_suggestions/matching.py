from collections.abc import Iterable

from hharon.usecases.headhunter_suggestions.constants import (
    THRESHOLD_DEFAULT,
    THRESHOLD_METRO,
    THRESHOLD_SKILL,
)
from hharon.usecases.headhunter_suggestions.normalize import normalize_for_matching
from hharon.usecases.headhunter_suggestions.scoring import similarity_between
from hharon_api.v1 import hharon_pb2


def _get_hh_normalized_texts(
    field: hharon_pb2.GetHeadhunterSuggestionsRequest.Field.ValueType, hh_item: dict[str, object]
) -> tuple[str, str | None]:
    """Нормализованный текст из HH (name/text) и при наличии — acronym (для вузов)."""
    hh_text = str(hh_item.get("name") or hh_item.get("text") or "")
    main = normalize_for_matching(field, hh_text)
    acronym: str | None = None
    acr = hh_item.get("acronym")
    if field == hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_EDUCATIONAL_INSTITUTION and acr is not None:
        acronym = normalize_for_matching(field, str(acr))
    return main, acronym


def compute_score(
    field: hharon_pb2.GetHeadhunterSuggestionsRequest.Field.ValueType, original_text: str, hh_item: dict[str, object]
) -> float:
    """Score of user text match with HH item (0-1)."""
    src = normalize_for_matching(field, original_text or "")
    hh_raw, hh_acronym = _get_hh_normalized_texts(field, hh_item)
    if not hh_raw:
        return 0.0
    score_main = similarity_between(src, hh_raw)
    if hh_acronym is not None:
        score_main = max(score_main, similarity_between(src, hh_acronym))
    return max(0.0, min(1.0, score_main))


def threshold_for(field: hharon_pb2.GetHeadhunterSuggestionsRequest.Field.ValueType) -> float:
    """Порог, выше которого считаем матч по HH успешным."""
    if field == hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_METRO:
        return THRESHOLD_METRO
    if field == hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL:
        return THRESHOLD_SKILL
    return THRESHOLD_DEFAULT


def select_best_candidate(
    candidates: Iterable[tuple[dict[str, object], float]],
) -> tuple[dict[str, object] | None, float]:
    """Pick candidate with maximum score."""
    best_item: dict[str, object] | None = None
    best_score = 0.0
    for item, score in candidates:
        if score > best_score:
            best_item, best_score = item, score
    return best_item, best_score
