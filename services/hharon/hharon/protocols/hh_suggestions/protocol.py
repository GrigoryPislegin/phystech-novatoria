from abc import ABC, abstractmethod

import pydantic

from hharon.domain.headhunter_suggestions import SuggestionItem
from hharon_api.v1 import hharon_pb2


class HHSuggestionsError(Exception):
    """Error when working with HH suggestions."""


class HHSuggestionsProtocol(ABC):
    """Fetches a list of suggestions from HH by field and search text."""

    class FetchSuggestionsRequest(pydantic.BaseModel):
        field: hharon_pb2.GetHeadhunterSuggestionsRequest.Field.ValueType
        text: str
        limit: int = 20

    @abstractmethod
    async def fetch_suggestions(self, request: "HHSuggestionsProtocol.FetchSuggestionsRequest") -> list[SuggestionItem]:
        """Returns a list of suggestion items (id, name/text, etc.) for matching."""
        ...
