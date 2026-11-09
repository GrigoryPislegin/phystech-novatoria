from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

import pydantic

from hharon.domain.scalars import (
    ResponseCollectionSettingsID,
    SearchCampaignID,
    TaskID,
)


class OutboxTaskStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    SUCCEEDED = "SUCCEEDED"
    CANCELLED = "CANCELLED"


class OutboxTaskType(StrEnum):
    TOKEN_UPDATE = "token_update"  # noqa: S105
    RESPONSE_COLLECTION = "response_collection"
    RESUME_SEARCH_SCAN = "resume_search_scan"


class TokenUpdatePayload(pydantic.BaseModel):
    """Payload for TOKEN_UPDATE outbox task."""

    user_id: str


class ResponseCollectionPayload(pydantic.BaseModel):
    """Payload for RESPONSE_COLLECTION outbox task."""

    settings_id: ResponseCollectionSettingsID


class ResumeSearchScanPayload(pydantic.BaseModel):
    """Payload for RESUME_SEARCH_SCAN outbox task."""

    campaign_id: SearchCampaignID


@dataclass(frozen=True)
class OutboxTask:
    id: TaskID
    task_type: OutboxTaskType
    payload: dict[str, Any]  # pyright: ignore[reportExplicitAny]
    created_at: datetime
    updated_at: datetime
    available_at: datetime
    attempts: int
    status: OutboxTaskStatus
