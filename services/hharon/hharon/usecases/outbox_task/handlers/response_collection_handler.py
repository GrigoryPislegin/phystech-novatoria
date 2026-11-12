import random
import string
from datetime import UTC, datetime, timedelta
from typing import final

import structlog

import hharon.pkg.nanimai_platform.platform_api.v1 as platform_api
from hharon.domain import KnownCandidateSourceEnum, OutboxTaskType, ResponseCollectionStatus
from hharon.domain.outbox_task import OutboxTask, OutboxTaskStatus, ResponseCollectionPayload
from hharon.domain.response_collection import ResponseCollectionSettings
from hharon.domain.scalars import ResponseCollectionSettingsID
from hharon.infra.platform import CREATE_CANDIDATE_QUEUE
from hharon.infra.response_collection import ResponseCollectionConfig
from hharon.pkg.hhapi import CurrencyEnum, PreferredContactTypeEnum, ResumeResumeForEmployer
from hharon.protocols import response_collection as response_collection_protocol
from hharon.protocols import token as token_protocol
from hharon.protocols.outbox_task import OutboxContext
from hharon.protocols.outbox_task.protocol import OutboxTaskRepositoryProtocol
from hharon.usecases.message_queue import MessageQueuePushUsecase
from hharon.usecases.outbox_task.usecase import OutboxUsecase
from hharon.usecases.resume_formatter.resume_formatter import ResumeFormatter
from hharon.usecases.token.get_tokens import GetTokens, GetTokensNotFoundError

log = structlog.stdlib.get_logger("hharon.usecases.outbox_task.handlers.ResponseCollectionHandler")


class ResponseCollectionHandlerError(Exception):
    """Base exception class for ResponseCollectionHandler errors."""


class ResponseCollectionHandlerNotFoundError(ResponseCollectionHandlerError):
    """Settings not found error."""


class ResponseCollectionHandlerAccessDeniedError(ResponseCollectionHandlerError):
    """Access denied error - task should be failed."""


@final
class ResponseCollectionHandler[SessionT]:
    """Handler for RESPONSE_COLLECTION outbox tasks."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        response_collection_repository: response_collection_protocol.ResponseCollectionRepositoryProtocol[SessionT],
        token_repository: token_protocol.HeadHunterTokenRepositoryProtocol[SessionT],
        get_tokens_usecase: GetTokens[SessionT],
        hh_client: response_collection_protocol.ResponseCollectionHHApiProtocol,
        outbox_usecase: OutboxUsecase[SessionT],
        outbox_repo: OutboxTaskRepositoryProtocol[SessionT],
        config: ResponseCollectionConfig,
        message_queue: MessageQueuePushUsecase,
        formatter: ResumeFormatter,
    ) -> None:
        self._response_collection_repository = response_collection_repository
        self._token_repository = token_repository
        self._get_tokens_usecase = get_tokens_usecase
        self._outbox_usecase = outbox_usecase
        self._outbox_repo = outbox_repo
        self._config = config
        self._hh_client = hh_client
        self._message_queue = message_queue
        self._formatter = formatter

    async def handle(
        self,
        *,
        ctx: OutboxContext[SessionT],
        task: OutboxTask,
    ) -> None:
        """Handle a RESPONSE_COLLECTION outbox task execution.

        Args:
            ctx: Outbox context with session
            task: The task to handle
        """
        payload = self._parse_task_payload(task)
        settings = await self._get_settings(ctx=ctx, settings_id=payload.settings_id, task_id=str(task.id))

        if settings.status != ResponseCollectionStatus.ACTIVE:
            return

        try:
            await self._process_response_collection(ctx=ctx, task=task, settings=settings)
        except ResponseCollectionHandlerNotFoundError:
            raise
        except ResponseCollectionHandlerAccessDeniedError:
            # Already handled and task failed
            raise
        except GetTokensNotFoundError:
            # Tokens not found - fail task and settings
            log.warning(
                "tokens not found, failing task and settings",
                task_id=task.id,
                settings_id=settings.id,
                user_id=settings.user_id,
            )
            await self._fail_task_and_settings(task=task, settings_id=settings.id)
            raise ResponseCollectionHandlerError("tokens not found") from None
        except response_collection_protocol.HeadHunterRateLimitError as e:
            await self._handle_rate_limit(task=task, error=e)
            raise  # Re-raise to prevent task from being marked as succeeded
        except response_collection_protocol.HeadHunterAccessDeniedError:
            # This should only happen for resume access, collection access is handled inside
            await self._handle_resume_access_error(task=task)
            raise  # Re-raise to prevent task from being marked as succeeded
        except response_collection_protocol.HeadHunterResponseCollectionError:
            await self._handle_resume_access_error(task=task)
            raise  # Re-raise to prevent task from being marked as succeeded
        except Exception as e:
            log.exception("unexpected error in response collection handler", task_id=task.id, settings_id=settings.id)
            raise ResponseCollectionHandlerError("unexpected error") from e

    def _parse_task_payload(self, task: OutboxTask) -> ResponseCollectionPayload:
        """Parse task payload and return ResponseCollectionPayload."""
        try:
            return ResponseCollectionPayload.model_validate(task.payload)
        except Exception as e:
            log.exception("failed to parse task payload", task_id=task.id, payload=task.payload)
            raise ResponseCollectionHandlerError("failed to parse task payload") from e

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

    async def _process_response_collection(
        self, *, ctx: OutboxContext[SessionT], task: OutboxTask, settings: ResponseCollectionSettings
    ) -> None:
        """Process response collection: collect responses, process candidates."""
        if self._check_retry_limit(task=task):
            await self._fail_task_on_max_retries(task=task)
            return

        log.debug("Handling response collection task", task_id=task.id, settings_id=settings.id)

        tokens_response = await self._get_tokens_usecase.get_tokens(
            GetTokens.GetTokensRequest(user_id=settings.user_id)
        )
        processed_count = await self._process_multiple_collections(
            task=task,
            settings=settings,
            access_token=tokens_response.access_token,
        )

        # Reschedule task for 1 hour on success
        await self._schedule_new_task(
            ctx=ctx,
            task_type=OutboxTaskType.RESPONSE_COLLECTION,
            payload=ResponseCollectionPayload(settings_id=settings.id).model_dump(mode="json"),
            backoff=timedelta(hours=1),
        )
        log.info(
            "Successfully handled response collection task",
            task_id=task.id,
            settings_id=settings.id,
            processed_count=processed_count,
        )

    async def _get_settings(
        self, *, ctx: OutboxContext[SessionT], settings_id: ResponseCollectionSettingsID, task_id: str
    ) -> ResponseCollectionSettings:
        """Get settings by ID or raise error if not found."""
        settings = await self._response_collection_repository.get_settings(
            ctx.session,
            response_collection_protocol.ResponseCollectionRepositoryProtocol.GetSettingsRequest(
                settings_id=settings_id
            ),
        )

        if settings is None:
            log.warning("Settings not found", task_id=task_id, settings_id=settings_id)
            error_msg = f"Settings not found for settings_id: {settings_id}"
            raise ResponseCollectionHandlerNotFoundError(error_msg)

        return settings

    async def _process_multiple_collections(
        self,
        *,
        task: OutboxTask,
        settings: ResponseCollectionSettings,
        access_token: str,
    ) -> int:
        """Process responses from all collections."""
        processed_count = 0
        max_responses = self._config.max_responses_per_session

        for collection_id in settings.headhunter_collections:
            if processed_count >= max_responses:
                log.info("reached max responses limit", processed_count=processed_count, max_responses=max_responses)
                break

            try:
                processed_in_collection = await self._process_collection(
                    collection_id=collection_id,
                    settings=settings,
                    access_token=access_token,
                    processed_count=processed_count,
                    max_responses=max_responses,
                )
                processed_count += processed_in_collection
            except response_collection_protocol.HeadHunterAccessDeniedError:
                # Collection access denied - fail task and settings
                log.exception("collection access denied, failing task", collection_id=collection_id)
                await self._fail_task_and_settings(task=task, settings_id=settings.id)
                raise ResponseCollectionHandlerAccessDeniedError("Access denied to collection") from None
            except response_collection_protocol.HeadHunterRateLimitError:
                # Rate limit - will be handled by outer handler
                raise

        return processed_count

    async def _process_collection(
        self,
        *,
        collection_id: str,
        settings: ResponseCollectionSettings,
        access_token: str,
        processed_count: int,
        max_responses: int,
    ) -> int:
        """Process responses from a single collection."""
        collection_processed = 0

        async for response_item in self._hh_client.get_responses_from_collection(
            collection_id=collection_id, vacancy_id=settings.headhunter_vacancy_id, access_token=access_token
        ):
            if processed_count + collection_processed >= max_responses:
                break

            if response_item.resume is None:
                log.warning("response item has no resume", response_item=response_item)
                continue

            if not response_item.resume.id:
                log.warning("response item resume has no id", response_item=response_item)
                continue

            resume_id = response_item.resume.id

            async with self._response_collection_repository.context() as session:
                is_processed = await self._response_collection_repository.is_candidate_processed(
                    session,
                    response_collection_protocol.ResponseCollectionRepositoryProtocol.IsCandidateProcessedRequest(
                        resume_id=resume_id,
                        settings_id=settings.id,
                    ),
                )

                if is_processed:
                    log.debug("candidate already processed", resume_id=resume_id)
                    continue

                # Mark candidate as processed (idempotent: None if already processed by search or other run)
                marked = await self._response_collection_repository.mark_candidate_processed(
                    session,
                    response_collection_protocol.ResponseCollectionRepositoryProtocol.MarkCandidateProcessedRequest(
                        resume_id=resume_id,
                        vacancy_id=settings.vacancy_id,
                        source=KnownCandidateSourceEnum.RESPONSE_COLLECTION,
                        source_id=settings.id,
                    ),
                )
                if marked is None:
                    log.debug("candidate already processed", resume_id=resume_id)
                    continue

                full_resume = await self._hh_client.get_resume(resume_id=resume_id, access_token=access_token)
                collection_processed += 1
                log.info(
                    "candidate processed, should be sent to queue",
                    resume_id=resume_id,
                    vacancy_id=settings.vacancy_id,
                )

                _ = await self._message_queue.push(
                    CREATE_CANDIDATE_QUEUE, bytes(self._map_to_request(full_resume, settings.vacancy_id))
                )

        return collection_processed

    async def _handle_rate_limit(
        self, *, task: OutboxTask, error: response_collection_protocol.HeadHunterRateLimitError
    ) -> None:
        """Handle rate limit error by rescheduling task for 4 hours in a separate transaction."""
        log.warning("rate limit error, rescheduling task", task_id=task.id, retry_after=error.retry_after)
        await self._reschedule_task_in_separate_transaction(task=task, backoff=timedelta(hours=4))

    async def _handle_resume_access_error(
        self,
        *,
        task: OutboxTask,
    ) -> None:
        """Handle resume access error by rescheduling task for 8 hours in a separate transaction."""
        log.warning("resume access error, rescheduling task", task_id=task.id)
        await self._reschedule_task_in_separate_transaction(task=task, backoff=timedelta(hours=8))

    async def _schedule_new_task(
        self,
        *,
        ctx: OutboxContext[SessionT],
        task_type: OutboxTaskType,
        payload: dict[str, object],
        backoff: timedelta,
    ) -> None:
        """Schedule new task with delay in current transaction."""
        new_available_at = datetime.now(UTC) + backoff
        task = await self._outbox_usecase.schedule_task(
            ctx=ctx,
            request=OutboxUsecase[SessionT].ScheduleTaskRequest(
                task_type=task_type,
                available_at=new_available_at,
                payload=payload,
            ),
        )
        log.info("new task scheduled", task_id=task.id, new_available_at=new_available_at, backoff=backoff)

    async def _reschedule_task_in_separate_transaction(self, *, task: OutboxTask, backoff: timedelta) -> None:
        """Reschedule task with delay in a separate transaction to avoid rollback."""
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
            "task rescheduled in separate transaction",
            task_id=task.id,
            new_available_at=new_available_at,
            backoff=backoff,
        )

    async def _fail_task_and_settings(self, *, task: OutboxTask, settings_id: ResponseCollectionSettingsID) -> None:
        """Mark task and settings as failed in a single transaction."""
        async with self._outbox_repo.context() as session:
            _ = await self._outbox_repo.update_task(
                session,
                OutboxTaskRepositoryProtocol.UpdateTaskRequest(
                    id=task.id,
                    status=OutboxTaskStatus.FAILED,
                ),
            )
            _ = await self._response_collection_repository.update_settings_status(
                session,
                response_collection_protocol.ResponseCollectionRepositoryProtocol.UpdateSettingsStatusRequest(
                    settings_id=settings_id,
                    status=ResponseCollectionStatus.FAILED,
                ),
            )  # type: ignore[func-returns-value]
        log.info(
            "task and settings marked as failed",
            task_id=task.id,
            settings_id=settings_id,
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

        request.source = platform_api.CandidateSource.HH
        request.skills = [platform_api.Skill(title=skill) for skill in resume.skill_set]
        request.status = platform_api.VacancyStage.MAGIC_AI

        return request

    def _map_currency(self, currency: CurrencyEnum) -> str:
        if currency == CurrencyEnum.BYR:
            return "BYN"
        if currency == CurrencyEnum.RUR:
            return "RUB"

        return currency.value
