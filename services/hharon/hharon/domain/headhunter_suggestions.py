from typing import ClassVar, Protocol, runtime_checkable

import pydantic


class Suggestion(pydantic.BaseModel):
    """Single suggestion result for the client (id, text, score)."""

    model_config: ClassVar[pydantic.ConfigDict] = pydantic.ConfigDict(frozen=True)

    item_id: str
    """HeadHunter item ID when matched; or generated UUID (prefix custom:) for custom."""
    text: str
    """Display label."""
    score: float = pydantic.Field(default=0.0, ge=0.0, le=1.0)
    """Match score (0–1)."""

    @property
    def id(self) -> str:
        """Identifier for API/frontend; HH item id or generated id for custom."""
        return self.item_id

    @property
    def is_custom(self) -> bool:
        """True if the suggestion was created locally (not from HH)."""
        return self.item_id.startswith("custom:")


class MetroStationItem(pydantic.BaseModel):
    """Metro station suggestion item (id, name, line, city)."""

    id: str
    name: str
    text: str
    line_id: str | None = None
    line_name: str | None = None
    city_id: str
    city_name: str


@runtime_checkable
class _HHItemLike(Protocol):
    """Protocol for HH API items (skill_set, areas, professional_roles, etc.). id и text обязательны."""

    id: str
    text: str


class SuggestionItem(pydantic.BaseModel):
    """HH suggestion item: id, name/text, optional acronym (e.g. for universities)."""

    id: str
    name: str
    text: str
    acronym: str | None = None

    @classmethod
    def from_hh_item(cls, item: _HHItemLike, *, acronym: str | None = None) -> "SuggestionItem":
        """Build from HH API item (skill_set, areas, professional_roles, educational_institutions)."""
        id_ = str(item.id)
        label = str(item.text)
        acr = acronym if acronym is not None else getattr(item, "acronym", None)
        acr = acr if isinstance(acr, str) else None
        return cls(id=id_, name=label, text=label, acronym=acr)
