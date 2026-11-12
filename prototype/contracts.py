from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Requirement(StrictModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    mandatory_quote: str | None

    @property
    def weight(self):
        return 3 if self.mandatory_quote else 1


class Requirements(StrictModel):
    items: list[Requirement] = Field(min_length=1, max_length=80)

    def validate_source(self, source):
        unique_ids(self.items)
        seen = set()
        for item in self.items:
            exact_quote(item.quote, source)
            identity = (item.text.strip().casefold(), item.quote.strip().casefold())
            if identity in seen:
                raise ValueError('duplicate_requirement')
            seen.add(identity)
            if item.mandatory_quote is not None:
                exact_quote(item.mandatory_quote, source)
                # A heading must be quoted together with its requirement, not alone.
                # This binds spans structurally; semantic mandatory status still needs review.
                if len(item.mandatory_quote.strip()) < 8 or item.quote not in item.mandatory_quote:
                    raise ValueError('unbound_mandatory_quote')


class Fact(StrictModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class Facts(StrictModel):
    items: list[Fact] = Field(max_length=150)

    def validate_source(self, source):
        unique_ids(self.items)
        for item in self.items:
            exact_quote(item.quote, source)


class Row(StrictModel):
    requirement_id: str
    status: Literal['full', 'partial', 'fail', 'unknown']
    fact_ids: list[str]
    comment: str = Field(min_length=1)
    question: str | None


class Evaluation(StrictModel):
    rows: list[Row] = Field(min_length=1, max_length=80)


def unique_ids(items):
    ids = [x.id for x in items]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate_ids')


def exact_quote(quote, source):
    if not quote.strip() or quote not in source:
        raise ValueError('unverified_quote')


def validate_pair(requirements, facts, evaluation):
    expected = {x.id for x in requirements.items}
    actual = [x.requirement_id for x in evaluation.rows]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError('requirement_coverage')
    fact_ids = {x.id for x in facts.items}
    for row in evaluation.rows:
        if len(row.fact_ids) != len(set(row.fact_ids)) or not set(row.fact_ids) <= fact_ids:
            raise ValueError('invalid_fact_reference')
        if row.status == 'unknown' and row.fact_ids:
            raise ValueError('unknown_with_evidence')
        if row.status != 'unknown' and not row.fact_ids:
            raise ValueError('missing_evidence')
        if row.status != 'full' and not (row.question and row.question.strip()):
            raise ValueError('missing_question')
