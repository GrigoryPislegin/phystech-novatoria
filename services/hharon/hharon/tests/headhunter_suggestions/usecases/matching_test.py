"""Unit-тесты логики матчинга (нормализация, скоринг, порог) без HH API."""

import pytest

from hharon.usecases.headhunter_suggestions import matching
from hharon.usecases.headhunter_suggestions.matching import select_best_candidate
from hharon_api.v1 import hharon_pb2


@pytest.mark.parametrize(
    ("field", "text", "expected_contains"),
    [
        (
            hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL,
            "пайтон",
            "pajton",
        ),  # транслитерация ru -> latin
        (hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL, "Python", "python"),
        (hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_METRO, "Кожуховская метро", "кожуховская"),
        (hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_METRO, "  Аннино  станция  ", "аннино"),
        (hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_CITIZENSHIP, "гражданство Россия", "россия"),
        (hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_CITIZENSHIP, "гражданин РФ", "рф"),
        (hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_EDUCATIONAL_INSTITUTION, "МГУ университет", "мгу"),
        (hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_EDUCATIONAL_INSTITUTION, "вышка", "вышка"),
    ],
)
def test_normalize_for_matching(
    field: hharon_pb2.GetHeadhunterSuggestionsRequest.Field.ValueType, text: str, expected_contains: str
) -> None:
    result = matching.normalize_for_matching(field, text)
    assert expected_contains in result or result in expected_contains


def test_normalize_educational_institution_strip_suffix() -> None:
    """Срезаются суффиксы (университет, институт, академия), без словарей аббревиатур."""
    assert "мгу" in matching.normalize_for_matching(
        hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_EDUCATIONAL_INSTITUTION, "МГУ университет"
    )
    assert (
        matching.normalize_for_matching(
            hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_EDUCATIONAL_INSTITUTION, "вышка"
        )
        == "вышка"
    )


def test_threshold_for_fields() -> None:
    assert matching.threshold_for(hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_METRO) == 0.9
    assert matching.threshold_for(hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL) == 0.8
    assert matching.threshold_for(hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_CITIZENSHIP) == 0.85


def test_compute_score_exact_match() -> None:
    score = matching.compute_score(
        hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL,
        "Python",
        {"id": "1114", "name": "Python", "text": "Python"},
    )
    assert score >= 0.95


def test_compute_score_partial_match() -> None:
    score = matching.compute_score(
        hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_METRO,
        "Кожуховская",
        {"id": "10.52", "name": "Кожуховская", "text": "Кожуховская"},
    )
    assert score >= 0.9


def test_compute_score_no_match() -> None:
    score = matching.compute_score(
        hharon_pb2.GetHeadhunterSuggestionsRequest.Field.FIELD_SKILL,
        "НесуществующийНавыкXyZ",
        {"id": "1", "name": "Python", "text": "Python"},
    )
    assert score < 0.5


def test_select_best_candidate() -> None:
    candidates: list[tuple[dict[str, object], float]] = [
        ({"id": "1", "text": "A"}, 0.5),
        ({"id": "2", "text": "B"}, 0.9),
        ({"id": "3", "text": "C"}, 0.7),
    ]
    best_item, best_score = select_best_candidate(candidates)
    assert best_item is not None
    assert best_item["id"] == "2"
    assert best_score == 0.9


def test_select_best_candidate_empty() -> None:
    best_item, best_score = select_best_candidate([])
    assert best_item is None
    assert best_score == 0.0
