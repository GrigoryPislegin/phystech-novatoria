from enum import StrEnum
from typing import ClassVar

import pydantic

from hharon.domain.scalars import ResponseCollectionSettingsID


class ResponseCollectionStatus(StrEnum):
    """Статус сбора откликов."""

    CREATED = "created"  # Создан, но еще не запущен
    ACTIVE = "active"  # Активен
    COMPLETED = "completed"  # Завершен
    FAILED = "failed"  # Провален


class ResponseCollectionSettings(pydantic.BaseModel):
    """Domain model for response collection settings."""

    model_config: ClassVar[pydantic.ConfigDict] = pydantic.ConfigDict(frozen=True)

    id: ResponseCollectionSettingsID
    vacancy_id: str
    user_id: str
    headhunter_vacancy_id: str
    headhunter_collections: list[str]
    status: ResponseCollectionStatus


class ProcessedCandidate(pydantic.BaseModel):
    """Domain model for processed candidate tracking."""

    model_config: ClassVar[pydantic.ConfigDict] = pydantic.ConfigDict(frozen=True)

    resume_id: str
    vacancy_id: str
