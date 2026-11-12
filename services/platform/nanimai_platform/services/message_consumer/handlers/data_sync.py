from __future__ import annotations

from typing import final, override

import structlog

from nanimai_platform import domain
from nanimai_platform.external_clients.tulpa.tulpa_api.v1 import CriteriaMatch, ExecutionStatus, FlowResultMessage
from nanimai_platform.protocols.external.message_queue import Message
from nanimai_platform.protocols.external.tulpa import TulpaProtocol
from nanimai_platform.services.llm import LLMService
from nanimai_platform.services.message_consumer.handlers.base import (
    MessageHandler,
    MessageHandlerError,
    MessageHandlerInvalidDataError,
)
from nanimai_platform.utils.logging_span import span

log = structlog.stdlib.get_logger("app.handler.DataSyncHandler")


@final
class DataSyncHandler(MessageHandler):
    QUEUE_NAME = "tulpa.results"
    HANDLER_NAME = "data_sync"

    def __init__(self, llm_service: LLMService):
        self._llm_service = llm_service

    @property
    @override
    def name(self) -> str:
        return self.HANDLER_NAME

    @property
    @override
    def queue_name(self) -> str:
        return self.QUEUE_NAME

    @span(op="data_sync_handler", name="handle")
    @override
    async def handle(self, message: Message) -> None:
        log.debug(
            "handling data sync message",
            delivery_tag=message.delivery_tag,
            routing_key=message.routing_key,
            body_size=len(message.body),
        )

        try:
            flow_result = FlowResultMessage().parse(message.body)
            log.debug(
                "unmarshaled message",
                message_id=flow_result.message_id,
                flow_kind=flow_result.flow_kind,
                status=flow_result.status,
            )

            if flow_result.analyse_candidate_output is not None:
                await self._process_analyse_candidate(flow_result)
            elif flow_result.extract_candidate_output is not None:
                await self._process_extract_candidate(flow_result)
            else:
                log.debug(
                    "message does not contain any handled output, skipping",
                    message_id=flow_result.message_id,
                    flow_kind=flow_result.flow_kind,
                )

        except Exception as e:
            log.warning(
                "failed to process data sync message",
                error=str(e),
                error_type=type(e).__name__,
                delivery_tag=message.delivery_tag,
                exc_info=True,
            )
            raise MessageHandlerError(f"Failed to process message: {e}") from e

    @span(op="data_sync_handler", name="process_analyse_candidate")
    async def _process_analyse_candidate(self, flow_result: FlowResultMessage) -> None:
        log.info(
            "processing analyse candidate message",
            message_id=flow_result.message_id,
            status=flow_result.status,
        )

        metadata = self._validate_and_extract_metadata(flow_result)

        if flow_result.status == ExecutionStatus.ERROR:
            log.warning(
                "flow execution failed",
                message_id=flow_result.message_id,
                error_message=flow_result.error_message,
            )
            await self._llm_service.finish_analyse_operation(
                LLMService.FinishAnalyseOperationRequest(
                    status="error",
                    metadata=metadata,
                    results=[],
                    error=flow_result.error_message,
                )
            )
            return

        if flow_result.analyse_candidate_output is None:
            log.warning("analyse_candidate_output is None despite being checked earlier")
            return

        results = []
        for output in flow_result.analyse_candidate_output.results:
            criterion_status = self._map_criteria_match(output.match)
            results.append(
                LLMService.FinishAnalyseResult(
                    factor_id=output.id,
                    status=criterion_status,
                    resume_summary=output.resume_summary,
                )
            )

        log.info(
            "calling llm_service.finish_analyse_operation",
            message_id=flow_result.message_id,
            results_count=len(results),
        )

        await self._llm_service.finish_analyse_operation(
            LLMService.FinishAnalyseOperationRequest(
                status="success",
                metadata=metadata,
                results=results,
                error=None,
            )
        )

        log.info(
            "successfully processed analyse candidate message",
            message_id=flow_result.message_id,
        )

    @span(op="data_sync_handler", name="process_extract_candidate")
    async def _process_extract_candidate(self, flow_result: FlowResultMessage) -> None:
        log.info(
            "processing extract candidate message",
            message_id=flow_result.message_id,
            status=flow_result.status,
        )

        metadata = self._validate_and_extract_metadata_for_extract_candidate(flow_result)

        if flow_result.status == ExecutionStatus.ERROR:
            log.warning(
                "flow execution failed",
                message_id=flow_result.message_id,
                error_message=flow_result.error_message,
            )
            await self._llm_service.finish_parse_candidate(
                LLMService.FinishParseCandidateRequest(
                    status="error",
                    metadata=metadata,
                    candidate_data=None,
                    error=flow_result.error_message,
                )
            )
            return

        if flow_result.extract_candidate_output is None or flow_result.extract_candidate_output.candidate is None:
            log.warning("extract_candidate_output or candidate is None")
            return

        candidate_data = flow_result.extract_candidate_output.candidate

        tulpa_candidate = None
        if candidate_data is not None:
            experience_years = 0
            experience_months = 0
            if candidate_data.experience is not None:
                experience_years = candidate_data.experience.years
                experience_months = candidate_data.experience.months

            tulpa_candidate = TulpaProtocol.TulpaCandidate(
                name=candidate_data.name,
                city=candidate_data.city,
                country=candidate_data.country,
                phone_number=candidate_data.phone_number,
                email=candidate_data.email,
                experience_years=experience_years,
                experience_months=experience_months,
                expected_salary=candidate_data.expected_salary,
                skills=list(candidate_data.skills),
                resume=candidate_data.resume,
            )

        log.info(
            "calling llm_service.finish_parse_candidate",
            message_id=flow_result.message_id,
        )

        await self._llm_service.finish_parse_candidate(
            LLMService.FinishParseCandidateRequest(
                status="success",
                metadata=metadata,
                candidate_data=tulpa_candidate,
                error=None,
            )
        )

        log.info(
            "successfully processed extract candidate message",
            message_id=flow_result.message_id,
        )

    def _validate_and_extract_metadata(self, flow_result: FlowResultMessage) -> dict[str, str]:
        if flow_result.metadata is None:
            log.error("metadata is missing in flow result", message_id=flow_result.message_id)
            raise MessageHandlerInvalidDataError("metadata is missing")

        metadata = flow_result.metadata.to_dict()

        required_fields = ["transaction_id", "operation_id", "candidate_id"]
        missing_fields = [field for field in required_fields if field not in metadata]

        if missing_fields:
            log.error(
                "metadata missing required fields",
                message_id=flow_result.message_id,
                missing_fields=missing_fields,
                metadata=metadata,
            )
            raise MessageHandlerInvalidDataError(f"metadata missing required fields: {missing_fields}")

        log.debug(
            "metadata validated",
            message_id=flow_result.message_id,
            metadata_keys=list(metadata.keys()),
        )

        return metadata

    def _validate_and_extract_metadata_for_extract_candidate(self, flow_result: FlowResultMessage) -> dict[str, str]:
        if flow_result.metadata is None:
            log.error("metadata is missing in flow result", message_id=flow_result.message_id)
            raise MessageHandlerInvalidDataError("metadata is missing")

        metadata = flow_result.metadata.to_dict()

        required_fields = ["user_id", "project_id", "vacancy_id", "operation_id"]
        missing_fields = [field for field in required_fields if field not in metadata]

        if missing_fields:
            log.error(
                "metadata missing required fields",
                message_id=flow_result.message_id,
                missing_fields=missing_fields,
                metadata=metadata,
            )
            raise MessageHandlerInvalidDataError(f"metadata missing required fields: {missing_fields}")

        log.debug(
            "metadata validated",
            message_id=flow_result.message_id,
            metadata_keys=list(metadata.keys()),
        )

        return metadata

    def _map_criteria_match(self, match: CriteriaMatch) -> domain.CriterionStatusEnum:
        match_mapping = {
            CriteriaMatch.FULL_MATCH: domain.CriterionStatusEnum.FULL,
            CriteriaMatch.PARTIAL_MATCH: domain.CriterionStatusEnum.PARTIAL,
            CriteriaMatch.NOT_MENTIONED: domain.CriterionStatusEnum.UNKNOWN,
            CriteriaMatch.MISMATCH: domain.CriterionStatusEnum.FAIL,
            CriteriaMatch.UNSPECIFIED: domain.CriterionStatusEnum.UNKNOWN,
        }

        mapped_status = match_mapping.get(match)
        if mapped_status is None:
            log.warning("unknown criteria match value, defaulting to UNKNOWN", match=match)
            return domain.CriterionStatusEnum.UNKNOWN

        return mapped_status
