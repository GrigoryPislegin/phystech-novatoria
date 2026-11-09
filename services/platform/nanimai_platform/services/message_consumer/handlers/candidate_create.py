from __future__ import annotations

from typing import final, override

import structlog
from pydantic_core import Url
from pydantic_extra_types.currency_code import ISO4217 as CurrencyISO4217

import platform_api.v1.candidate_api_pb2 as candidate_api_pb2
from nanimai_platform.domain import CandidateSourceEnum, ExpectedSalary, Skill, VacancyID
from nanimai_platform.protocols.external.message_queue import Message
from nanimai_platform.services.candidate import CandidateService, CandidateServiceError
from nanimai_platform.services.llm import LLMService
from nanimai_platform.services.message_consumer.handlers.base import (
    MessageHandler,
    MessageHandlerError,
    MessageHandlerInvalidDataError,
)
from nanimai_platform.services.vacancy import VacancyService
from nanimai_platform.utils.logging_span import span

log = structlog.stdlib.get_logger("app.handler.CandidateCreateHandler")


@final
class CandidateCreateHandler(MessageHandler):
    QUEUE_NAME = "platform.create_candidate"
    HANDLER_NAME = "candidate_create"
    PREFETCH_COUNT = 1

    def __init__(
        self,
        candidate_service: CandidateService,
        vacancy_service: VacancyService,
        llm_service: LLMService,
    ):
        self._candidate_service = candidate_service
        self._vacancy_service = vacancy_service
        self._llm_service = llm_service

    @property
    @override
    def name(self) -> str:
        return self.HANDLER_NAME

    @property
    @override
    def queue_name(self) -> str:
        return self.QUEUE_NAME

    @property
    @override
    def prefetch_count(self) -> int:
        return self.PREFETCH_COUNT

    @span(op="candidate_create_handler", name="handle")
    @override
    async def handle(self, message: Message) -> None:
        log.debug(
            "handling candidate create message",
            delivery_tag=message.delivery_tag,  # pyright: ignore[reportAny]
            routing_key=message.routing_key,
            body_size=len(message.body),
        )

        try:
            grpc_request = candidate_api_pb2.CreateCandidateRequest.FromString(message.body)

            try:
                vacancy_id = VacancyID(grpc_request.vacancy_id)
            except Exception as e:
                log.error("error parsing vacancy_id from message body", err=e)
                raise MessageHandlerInvalidDataError("invalid vacancy_id") from e

            # enrich data
            vacancy = await self._vacancy_service.read(self._vacancy_service.ReadVacancyRequest(id=vacancy_id))

            source = {
                candidate_api_pb2.CandidateSource.CANDIDATE_SOURCE_HH: CandidateSourceEnum.HH,
                candidate_api_pb2.CandidateSource.CANDIDATE_SOURCE_NANIMAI: CandidateSourceEnum.NANIMAI,
                candidate_api_pb2.CandidateSource.CANDIDATE_SOURCE_HH_SEARCH_CAMPAIGN: CandidateSourceEnum.HH_SEARCH_CAMPAIGN,
                candidate_api_pb2.CandidateSource.CANDIDATE_SOURCE_NANIMAI_JOBBOARD: CandidateSourceEnum.NANIMAI_JOBBOARD,
            }

            try:
                candidate = await self._candidate_service.create(
                    self._candidate_service.CreateCandidateRequest(
                        user_id=vacancy.user_id,
                        project_id=vacancy.project_id,
                        vacancy_id=vacancy.id,
                        resume=grpc_request.resume,
                        name=grpc_request.name,
                        city=grpc_request.city if grpc_request.HasField("city") else None,
                        country=grpc_request.country if grpc_request.HasField("country") else None,
                        phone_number=grpc_request.phone_number if grpc_request.HasField("phone_number") else None,
                        email=grpc_request.email if grpc_request.HasField("email") else None,
                        website=Url(grpc_request.website) if grpc_request.HasField("website") else None,
                        experience=grpc_request.experience,
                        expected_salary=ExpectedSalary(
                            currency=CurrencyISO4217(
                                grpc_request.expected_salary.currency
                                if grpc_request.expected_salary.currency
                                else "RUB"
                            ),
                            value=grpc_request.expected_salary.value,
                        )
                        if grpc_request.HasField("expected_salary") and grpc_request.expected_salary.value > 0
                        else None,
                        notes=grpc_request.notes,
                        source=source[grpc_request.source],
                        skills=[Skill(title=skill.title) for skill in grpc_request.skills],
                    )
                )
            except Exception as e:
                log.error("error creating candidate domain model", err=e)
                raise MessageHandlerInvalidDataError("invalid candidate data") from e

            log.info(
                "candidate created successfully",
                candidate_id=str(candidate.id),
                vacancy_id=str(candidate.vacancy_id),
            )

            try:
                operation_id = await self._llm_service.new_analyze_operation(
                    LLMService.NewAnalyzeOperationRequest(
                        user_id=candidate.user_id,
                        vacancy_id=candidate.vacancy_id,
                        candidate_id=candidate.id,
                    )
                )
                log.info(
                    "analysis operation started",
                    candidate_id=str(candidate.id),
                    operation_id=str(operation_id),
                )
            except Exception as e:
                log.warning(
                    "failed to start analysis for candidate",
                    candidate_id=str(candidate.id),
                    error=str(e),
                )

        except ValueError as e:
            log.error("invalid message data", error=str(e))
            raise MessageHandlerInvalidDataError(str(e)) from e
        except CandidateServiceError as e:
            log.error("failed to create candidate", error=str(e))
            raise MessageHandlerError(f"Failed to create candidate: {e}") from e
        except Exception as e:
            log.error("unexpected error handling candidate create message", error=str(e), exc_info=True)
            raise MessageHandlerError(f"Unexpected error: {e}") from e
