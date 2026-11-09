from enum import StrEnum
from typing import ClassVar
from uuid import UUID

import pydantic


class KnownCandidateSourceEnum(StrEnum):
    RESPONSE_COLLECTION = "RESPONSE_COLLECTION"
    SEARCH_CAMPAIGN = "SEARCH_CAMPAIGN"


class KnownCandidate(pydantic.BaseModel):
    model_config: ClassVar[pydantic.ConfigDict] = pydantic.ConfigDict(frozen=True)

    resume_id: str
    vacancy_id: str
    source: KnownCandidateSourceEnum
    source_id: UUID | None
