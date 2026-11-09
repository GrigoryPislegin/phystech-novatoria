from datetime import datetime
from enum import StrEnum
from typing import ClassVar

import pydantic

from hharon.domain.scalars import SearchCampaignID
from hharon.pkg import hhapi


class SearchCampaignStatus(StrEnum):
    """Статус поисковой кампании."""

    CREATED = "created"  # Создана, но еще не запущена
    ACTIVE = "active"  # Активна
    COMPLETED = "completed"  # Завершена
    FAILED = "failed"  # Провалена


class SearchCampaign(pydantic.BaseModel):
    model_config: ClassVar[pydantic.ConfigDict] = pydantic.ConfigDict(frozen=True)

    id: SearchCampaignID
    user_id: str
    vacancy_id: str
    status: SearchCampaignStatus

    active_until: datetime
    daily_limit: int

    search_params: list[hhapi.ResumesGetParameters]
