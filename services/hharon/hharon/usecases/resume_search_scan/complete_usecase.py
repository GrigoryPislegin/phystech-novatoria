from typing import final

import pydantic
import structlog

from hharon.domain.scalars import SearchCampaignID
from hharon.domain.search_campaign import SearchCampaignStatus
from hharon.protocols import resume_search_scan as resume_search_scan_protocol

log = structlog.stdlib.get_logger("hharon.usecases.CompleteSearchCampaignExecution")


class CompleteSearchCampaignExecutionError(Exception):
    """Base exception for CompleteSearchCampaignExecution errors."""


class CompleteSearchCampaignNotFoundError(CompleteSearchCampaignExecutionError):
    """Raised when the search campaign is not found."""


@final
class CompleteSearchCampaignExecution[SessionT]:
    def __init__(
        self,
        *,
        resume_search_scan_repository: resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol[SessionT],
    ) -> None:
        self._resume_search_scan_repository = resume_search_scan_repository

    class CompleteSearchCampaignExecutionRequest(pydantic.BaseModel):
        vacancy_id: str

    class CompleteSearchCampaignExecutionResponse(pydantic.BaseModel):
        vacancy_id: str

    async def complete(
        self, request: CompleteSearchCampaignExecutionRequest
    ) -> CompleteSearchCampaignExecutionResponse:
        """Complete resume search scan (search campaign)"""
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
                    raise CompleteSearchCampaignNotFoundError(msg)

                log.info(
                    "resuming search campaign",
                    campaign_id=campaign.id,
                )

                if (
                    campaign.status != SearchCampaignStatus.ACTIVE.value  # noqa: PLR1714
                    and campaign.status != SearchCampaignStatus.CREATED.value
                ):
                    log.warning(
                        "resume search scan is not active or created",
                        campaign_id=campaign.id,
                    )
                    return self.CompleteSearchCampaignExecutionResponse(vacancy_id=campaign.vacancy_id)

                await self._resume_search_scan_repository.update_campaign_status(
                    session,
                    resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol.UpdateCampaignStatusRequest(
                        campaign_id=SearchCampaignID.from_uuid(campaign.id),
                        status=SearchCampaignStatus.COMPLETED,
                    ),
                )

                log.info(
                    "resume search scan completed",
                    campaign_id=campaign.id,
                )
                return self.CompleteSearchCampaignExecutionResponse(vacancy_id=campaign.vacancy_id)

        except CompleteSearchCampaignExecutionError:
            raise
        except Exception as e:
            log.exception("unexpected error in complete resume search scan", error=str(e))
            raise CompleteSearchCampaignExecutionError("unexpected error") from e
