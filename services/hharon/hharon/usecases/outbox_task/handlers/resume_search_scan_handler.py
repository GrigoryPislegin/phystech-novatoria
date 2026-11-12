import random
import string
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import final

import structlog

import hharon.pkg.nanimai_platform.platform_api.v1 as platform_api
from hharon.domain import KnownCandidateSourceEnum, OutboxTaskType
from hharon.domain.outbox_task import OutboxTask, OutboxTaskStatus, ResumeSearchScanPayload
from hharon.domain.scalars import SearchCampaignID
from hharon.domain.search_campaign import SearchCampaign, SearchCampaignStatus
from hharon.infra.platform import CREATE_CANDIDATE_QUEUE
from hharon.infra.resume_search_scan import ResumeSearchScanConfig
from hharon.pkg.hhapi import CurrencyEnum, PreferredContactTypeEnum, ResumeResumeForEmployer
from hharon.protocols import resume_search_scan as resume_search_scan_protocol
from hharon.protocols import token as token_protocol
from hharon.protocols.outbox_task import OutboxContext
from hharon.protocols.outbox_task.protocol import OutboxTaskRepositoryProtocol
from hharon.usecases.message_queue import MessageQueuePushUsecase
from hharon.usecases.outbox_task.usecase import OutboxUsecase
from hharon.usecases.resume_formatter.resume_formatter import ResumeFormatter
from hharon.usecases.resume_search_scan.complete_usecase import CompleteSearchCampaignExecution
from hharon.usecases.token.get_tokens import GetTokens

log = structlog.stdlib.get_logger("hharon.usecases.outbox_task.handlers.ResumeSearchScanHandler")


class ResumeSearchScanHandlerError(Exception):
    """Base exception for ResumeSearchScanHandler errors."""


class ResumeSearchScanHandlerNotFoundError(ResumeSearchScanHandlerError):
    """Settings not found error."""


class ResumeSearchScanHandlerAccessDeniedError(ResumeSearchScanHandlerError):
    """Access denied error - task should be failed."""


@final
class ResumeSearchScanHandler[SessionT]:
    """Handler for RESUME_SEARCH_SCAN outbox tasks."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        resume_search_scan_repository: resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol[SessionT],
        token_repository: token_protocol.HeadHunterTokenRepositoryProtocol[SessionT],
        get_tokens_usecase: GetTokens[SessionT],
        hh_client: resume_search_scan_protocol.ResumeSearchScanHHApiProtocol,
        outbox_usecase: OutboxUsecase[SessionT],
        outbox_repo: OutboxTaskRepositoryProtocol[SessionT],
        config: ResumeSearchScanConfig,
        message_queue: MessageQueuePushUsecase,
        formatter: ResumeFormatter,
        complete_search_campaign_usecase: CompleteSearchCampaignExecution[SessionT],
    ) -> None:
        self._resume_search_scan_repository = resume_search_scan_repository
        self._token_repository = token_repository
        self._get_tokens_usecase = get_tokens_usecase
        self._hh_client = hh_client
        self._outbox_usecase = outbox_usecase
        self._outbox_repo = outbox_repo
        self._config = config
        self._message_queue = message_queue
        self._formatter = formatter
        self._complete_search_campaign_usecase = complete_search_campaign_usecase

    async def handle(
        self,
        *,
        ctx: OutboxContext[SessionT],
        task: OutboxTask,
    ) -> None:
        """Handle a RESUME_SEARCH_SCAN outbox task execution."""
        payload = self._parse_task_payload(task)
        campaign = await self._get_campaign(ctx=ctx, campaign_id=payload.campaign_id, task_id=str(task.id))

        if campaign.status != SearchCampaignStatus.ACTIVE:
            return

        if self._is_campaign_deadline_reached(task=task, campaign=campaign):
            await self._complete_campaign_and_succeed_task_in_separate_transaction(task=task, campaign=campaign)
            return

        try:
            await self._process_resume_search_scan(ctx=ctx, task=task, campaign=campaign)
        except ResumeSearchScanHandlerNotFoundError:
            raise
        except ResumeSearchScanHandlerAccessDeniedError:
            raise
        except resume_search_scan_protocol.HeadHunterRateLimitError as e:
            await self._handle_rate_limit(task=task, error=e)
            raise
        except resume_search_scan_protocol.HeadHunterAccessDeniedError:
            await self._fail_task_and_campaign(task=task, campaign_id=campaign.id)
            raise ResumeSearchScanHandlerAccessDeniedError("Access denied") from None
        except resume_search_scan_protocol.HeadHunterResumeSearchScanError:
            await self._fail_task_and_campaign(task=task, campaign_id=campaign.id)
            raise ResumeSearchScanHandlerAccessDeniedError("Resume search scan error") from None
        except Exception as e:
            log.exception(
                "unexpected error in resume search scan handler",
                task_id=task.id,
                campaign_id=campaign.id,
            )
            raise ResumeSearchScanHandlerError("unexpected error") from e

    def _parse_task_payload(self, task: OutboxTask) -> ResumeSearchScanPayload:
        try:
            return ResumeSearchScanPayload.model_validate(task.payload)
        except Exception as e:
            log.exception("failed to parse task payload", task_id=task.id, payload=task.payload)
            raise ResumeSearchScanHandlerError("failed to parse task payload") from e

    def _check_retry_limit(self, *, task: OutboxTask) -> bool:
        """True if max retries exceeded, False otherwise"""
        max_retries = self._config.max_retries
        if task.attempts >= max_retries:
            log.warning(
                "max retries exceeded, failing task",
                task_id=task.id,
                attempts=task.attempts,
                max_retries=max_retries,
            )
            return True
        return False

    async def _fail_task_on_max_retries(self, *, task: OutboxTask) -> None:
        """Mark task as failed when max retries is exceeded in a separate transaction."""
        async with self._outbox_repo.context() as session:
            _ = await self._outbox_repo.update_task(
                session,
                OutboxTaskRepositoryProtocol.UpdateTaskRequest(
                    id=task.id,
                    status=OutboxTaskStatus.FAILED,
                ),
            )
        log.info(
            "task marked as failed due to max retries",
            task_id=task.id,
            attempts=task.attempts,
        )

    async def _process_resume_search_scan(
        self,
        *,
        ctx: OutboxContext[SessionT],
        task: OutboxTask,
        campaign: SearchCampaign,
    ) -> None:
        if self._check_retry_limit(task=task):
            await self._fail_task_on_max_retries(task=task)
            return

        log.debug("Handling resume search scan task", task_id=task.id, campaign_id=campaign.id)

        tokens_response = await self._get_tokens_usecase.get_tokens(
            GetTokens.GetTokensRequest(user_id=campaign.user_id)
        )
        processed_count = await self._process_search(campaign=campaign, access_token=tokens_response.access_token)

        backoff = self._config.interval
        await self._schedule_new_task(
            ctx=ctx,
            task_type=OutboxTaskType.RESUME_SEARCH_SCAN,
            payload=ResumeSearchScanPayload(campaign_id=SearchCampaignID.from_uuid(campaign.id)).model_dump(
                mode="json"
            ),
            backoff=backoff,
        )
        log.info(
            "Successfully handled resume search scan task",
            task_id=task.id,
            campaign_id=campaign.id,
            processed_count=processed_count,
        )

    async def _get_campaign(
        self,
        *,
        ctx: OutboxContext[SessionT],
        campaign_id: SearchCampaignID,
        task_id: str,
    ) -> SearchCampaign:
        campaign = await self._resume_search_scan_repository.get_campaign(
            ctx.session,
            resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol.GetCampaignRequest(campaign_id=campaign_id),
        )

        if campaign is None:
            log.warning("Search campaign not found for resume scan", task_id=task_id, campaign_id=campaign_id)
            msg = "Search campaign not found for campaign_id: " + str(campaign_id)
            raise ResumeSearchScanHandlerNotFoundError(msg)

        return campaign

    def _is_campaign_deadline_reached(
        self,
        *,
        task: OutboxTask,
        campaign: SearchCampaign,
    ) -> bool:
        current_time = datetime.now(UTC)
        if current_time >= campaign.active_until:
            log.info(
                "Search campaign deadline reached",
                task_id=task.id,
                campaign_id=campaign.id,
                active_until=campaign.active_until,
                current_time=current_time,
            )
            return True
        return False

    async def _complete_campaign_and_succeed_task_in_separate_transaction(
        self,
        *,
        task: OutboxTask,
        campaign: SearchCampaign,
    ) -> None:
        async with self._outbox_repo.context() as session:
            _ = await self._outbox_repo.update_task(
                session,
                OutboxTaskRepositoryProtocol.UpdateTaskRequest(
                    id=task.id,
                    status=OutboxTaskStatus.SUCCEEDED,
                ),
            )
            await self._resume_search_scan_repository.update_campaign_status(
                session,
                resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol.UpdateCampaignStatusRequest(
                    campaign_id=SearchCampaignID.from_uuid(campaign.id),
                    status=SearchCampaignStatus.COMPLETED,
                ),
            )

        log.info(
            "Search campaign completed and task marked as succeeded",
            task_id=task.id,
            campaign_id=campaign.id,
        )

    async def _process_search(
        self,
        *,
        campaign: SearchCampaign,
        access_token: str,
    ) -> int:
        processed_count = 0
        max_per_run = ceil(campaign.daily_limit / self._config.scans_per_day)

        async for item in self._hh_client.get_resumes_from_search(
            access_token=access_token, params=campaign.search_params
        ):
            if processed_count >= max_per_run:
                log.debug("reached max_per_run limit", processed_count=processed_count, max_per_run=max_per_run)
                break

            resume_id = item.root.id
            if not resume_id:
                log.warning("resume search item has no id", item=item)
                continue

            async with self._resume_search_scan_repository.context() as session:
                is_processed = await self._resume_search_scan_repository.mark_candidate_processed(
                    session,
                    resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol.MarkCandidateProcessedRequest(
                        resume_id=resume_id,
                        vacancy_id=campaign.vacancy_id,
                        source=KnownCandidateSourceEnum.SEARCH_CAMPAIGN,
                        source_id=campaign.id,
                    ),
                )
                if is_processed is None:
                    log.debug("candidate already processed", resume_id=resume_id)
                    continue

                full_resume = await self._hh_client.get_resume(resume_id=resume_id, access_token=access_token)
                processed_count += 1
                log.info(
                    "candidate processed, sending to queue",
                    resume_id=resume_id,
                    vacancy_id=campaign.vacancy_id,
                )
                _ = await self._message_queue.push(
                    CREATE_CANDIDATE_QUEUE, bytes(self._map_to_request(full_resume, campaign.vacancy_id))
                )

        return processed_count

    async def _handle_rate_limit(
        self,
        *,
        task: OutboxTask,
        error: resume_search_scan_protocol.HeadHunterRateLimitError,
    ) -> None:
        log.warning("rate limit error, rescheduling task", task_id=task.id, retry_after=error.retry_after)
        backoff = self._config.interval
        await self._reschedule_task_in_separate_transaction(task=task, backoff=backoff)

    async def _fail_task_and_campaign(self, *, task: OutboxTask, campaign_id: SearchCampaignID) -> None:
        """Mark task and campaign as failed in a single transaction."""
        async with self._outbox_repo.context() as session:
            _ = await self._outbox_repo.update_task(
                session,
                OutboxTaskRepositoryProtocol.UpdateTaskRequest(
                    id=task.id,
                    status=OutboxTaskStatus.FAILED,
                ),
            )
            _ = await self._resume_search_scan_repository.update_campaign_status(
                session,
                resume_search_scan_protocol.ResumeSearchScanRepositoryProtocol.UpdateCampaignStatusRequest(
                    campaign_id=campaign_id,
                    status=SearchCampaignStatus.FAILED,
                ),
            )  # type: ignore[func-returns-value]
        log.info(
            "task and campaign marked as failed",
            task_id=task.id,
            campaign_id=campaign_id,
        )

    async def _schedule_new_task(
        self,
        *,
        ctx: OutboxContext[SessionT],
        task_type: OutboxTaskType,
        payload: dict[str, object],
        backoff: timedelta,
    ) -> None:
        new_available_at = datetime.now(UTC) + backoff
        new_task = await self._outbox_usecase.schedule_task(
            ctx=ctx,
            request=OutboxUsecase[SessionT].ScheduleTaskRequest(
                task_type=task_type,
                available_at=new_available_at,
                payload=payload,
            ),
        )
        log.info(
            "new resume search scan task scheduled",
            task_id=new_task.id,
            new_available_at=new_available_at,
            backoff=backoff,
        )

    async def _reschedule_task_in_separate_transaction(
        self,
        *,
        task: OutboxTask,
        backoff: timedelta,
    ) -> None:
        new_available_at = datetime.now(UTC) + backoff
        async with self._outbox_repo.context() as session:
            _ = await self._outbox_repo.update_task(
                session,
                OutboxTaskRepositoryProtocol.UpdateTaskRequest(
                    id=task.id,
                    available_at=new_available_at,
                    status=OutboxTaskStatus.PENDING,
                ),
            )
        log.info(
            "resume search scan task rescheduled in separate transaction",
            task_id=task.id,
            new_available_at=new_available_at,
            backoff=backoff,
        )

    def _map_to_request(self, resume: ResumeResumeForEmployer, vacancy_id: str) -> platform_api.CreateCandidateRequest:
        request = platform_api.CreateCandidateRequest()

        request.vacancy_id = vacancy_id

        request.resume = self._formatter.format_resume(resume)
        request.name = (
            f"{resume.first_name or ''} {resume.last_name or ''}".strip()
            or f"Кандидат {''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}"  # noqa: S311
        )
        request.city = resume.area.name if resume.area else None

        for contact in resume.contact:
            if contact.type.id == PreferredContactTypeEnum.EMAIL.value and (value := contact.contact_value):
                request.email = value

            if contact.type.id == PreferredContactTypeEnum.CELL.value and (value := contact.contact_value):
                request.phone_number = value

        request.website = resume.alternate_url
        request.experience = int(resume.total_experience.months or 0) if resume.total_experience else 0

        if resume.salary and resume.salary.amount:
            request.expected_salary = platform_api.ExpectedSalary(
                currency=self._map_currency(CurrencyEnum(resume.salary.currency or "RUR")),
                value=int(resume.salary.amount),
            )

        request.source = platform_api.CandidateSource.HH_SEARCH_CAMPAIGN
        request.skills = [platform_api.Skill(title=skill) for skill in resume.skill_set]
        request.status = platform_api.VacancyStage.MAGIC_AI

        return request

    def _map_currency(self, currency: CurrencyEnum) -> str:
        if currency == CurrencyEnum.BYR:
            return "BYN"
        if currency == CurrencyEnum.RUR:
            return "RUB"

        return currency.value
