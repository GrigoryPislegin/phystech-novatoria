from datetime import UTC, datetime
from typing import final

import pydantic
import structlog

from hharon.domain.outbox_task import OutboxTaskType, ResumeSearchScanPayload
from hharon.domain.scalars import SearchCampaignID
from hharon.domain.search_campaign import SearchCampaignStatus
from hharon.infra.resume_search_scan import ResumeSearchScanConfig
from hharon.protocols import resume_search_scan as resume_search_scan_protocol
from hharon.protocols.outbox_task import OutboxContext
from hharon.usecases.outbox_task.usecase import OutboxUsecase

log = structlog.stdlib.get_logger("hharon.usecases.InitSearchCampaignExecution")


class InitSearchCampaignExecutionError(Exception):
    """Base exception for InitSearchCampaignExecution errors."""


class InitSearchCampaignNotFoundError(InitSearchCampaignExecutionError):
    """Raised when the search campaign is not found."""


@final
class InitSearchCampaignExecution[SessionT]:
    def __init__(
        self,
        *,
        resume_search_scan_repository: resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol[SessionT],
        outbox_usecase: OutboxUsecase[SessionT],
        config: ResumeSearchScanConfig,
    ) -> None:
        self._resume_search_scan_repository = resume_search_scan_repository
        self._outbox_usecase = outbox_usecase
        self._config = config

    class InitSearchCampaignExecutionRequest(pydantic.BaseModel):
        vacancy_id: str

    class InitSearchCampaignExecutionResponse(pydantic.BaseModel):
        vacancy_id: str

    async def init(self, request: InitSearchCampaignExecutionRequest) -> InitSearchCampaignExecutionResponse:
        """Setup resume search scan (search campaign) and create task (first run delayed by config)."""
        try:
            async with self._resume_search_scan_repository.context() as session:
                campaign = await self._resume_search_scan_repository.get_campaign_by_vacancy(
                    session,
                    resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol.GetCampaignByVacancyRequest(
                        vacancy_id=request.vacancy_id
                    ),
                )

                if campaign is None:
                    msg = (
                        f"Search campaign not found for vacancy_id={request.vacancy_id}, "
                        "create it via CreateSearchCampaign first"
                    )
                    raise InitSearchCampaignNotFoundError(msg)

                log.info(
                    "resuming search campaign",
                    campaign_id=campaign.id,
                )

                await self._resume_search_scan_repository.update_campaign_status(
                    session,
                    resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol.UpdateCampaignStatusRequest(
                        campaign_id=SearchCampaignID.from_uuid(campaign.id),
                        status=SearchCampaignStatus.ACTIVE,
                    ),
                )
                available_at = datetime.now(UTC) + self._config.initial_delay_timedelta

                payload = ResumeSearchScanPayload(campaign_id=SearchCampaignID.from_uuid(campaign.id))
                task = await self._outbox_usecase.schedule_task(
                    ctx=OutboxContext(session=session),
                    request=OutboxUsecase[SessionT].ScheduleTaskRequest(
                        task_type=OutboxTaskType.RESUME_SEARCH_SCAN,
                        payload=payload.model_dump(mode="json"),
                        available_at=available_at,
                    ),
                )

                log.info(
                    "created resume search scan task",
                    task_id=task.id,
                    campaign_id=campaign.id,
                    available_at=available_at,
                )
                return self.InitSearchCampaignExecutionResponse(vacancy_id=campaign.vacancy_id)

        except InitSearchCampaignExecutionError:
            raise
        except Exception as e:
            log.exception("unexpected error in init resume search scan", error=str(e))
            raise InitSearchCampaignExecutionError("unexpected error") from e
