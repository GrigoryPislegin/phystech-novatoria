from typing import ClassVar

import pydantic


class ProcessedScanCandidate(pydantic.BaseModel):
    """Domain model for processed candidate tracking in resume search scan."""

    model_config: ClassVar[pydantic.ConfigDict] = pydantic.ConfigDict(frozen=True)

    resume_id: str
    vacancy_id: str
