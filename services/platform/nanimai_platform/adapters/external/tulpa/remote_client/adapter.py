from typing import final, override

import structlog
from grpclib.client import Channel
from grpclib.exceptions import GRPCError

from nanimai_platform import domain
from nanimai_platform.external_clients.tulpa.google.protobuf import Struct
from nanimai_platform.external_clients.tulpa.tulpa_api.v1 import (
    AnalyseCandidateAgainstCriteriaRequest,
    AnalyseCandidateAgainstCriteriaRequestCriterion,
    CriteriaImportance,
    DelayedTulpaServiceStub,
    Employment,
    ExtractCandidateFromRawRequest,
    ExtractVacancyFromRawRequest,
    GenerateVacancyCriteriaRequest,
    RequiredExperience,
    Schedule,
    UrgentTulpaServiceStub,
    WorkFormat,
)
from nanimai_platform.protocols.external.tulpa import TulpaError, TulpaGRPCError, TulpaProtocol
from nanimai_platform.utils import span

log = structlog.stdlib.get_logger("app.adapter.TulpaAdapter")


@final
class GRPCTulpaAdapter(TulpaProtocol):
    def __init__(self, host: str, port: int):
        self._grpc_channel = Channel(host, port)
        self._dstub = DelayedTulpaServiceStub(self._grpc_channel)
        self._ustub = UrgentTulpaServiceStub(self._grpc_channel)

    @span(op="tulpa_adapter", name="generate_vacancy_criteria")
    @override
    async def generate_vacancy_criteria(
        self, request: TulpaProtocol.GenerateVacancyCriteriaRequest
    ) -> TulpaProtocol.GenerateVacancyCriteriaResponse:
        grpc_request = GenerateVacancyCriteriaRequest(text=request.full_text)

        try:
            grpc_response = await self._ustub.generate_vacancy_criteria(grpc_request)

            criteria = []
            for grpc_criterion in grpc_response.criteria:
                initial_weight = 0

                if grpc_criterion.importance == CriteriaImportance.NESSASARY:
                    initial_weight = request.nessesary_weight
                elif grpc_criterion.importance == CriteriaImportance.BENEFICIAL:
                    initial_weight = request.beneficial_weight
                elif grpc_criterion.importance == CriteriaImportance.OPTIONAL:
                    initial_weight = request.optional_weight
                else:
                    initial_weight = 0

                criteria.append(
                    TulpaProtocol.TulpaCriterion(criterion=grpc_criterion.description, initial_weight=initial_weight)
                )

            return TulpaProtocol.GenerateVacancyCriteriaResponse(criteria=criteria)
        except GRPCError as e:
            log.error("failed to generate vacancy criteria with tulpa service", err=e)
            raise TulpaGRPCError.from_grpc(e) from e
        except Exception as e:
            log.error("failed to generate vacancy criteria with tulpa service", err=e)
            raise TulpaError("failed to generate vacancy criteria") from e

    @span(op="tulpa_adapter", name="extract_vacancy_from_raw")
    @override
    async def extract_vacancy_from_raw(self, raw_text: str) -> TulpaProtocol.TulpaVacancy:
        grpc_request = ExtractVacancyFromRawRequest(text=raw_text)

        try:
            grpc_response = await self._ustub.extract_vacancy_from_raw(grpc_request)
            if grpc_response.vacancy is None:
                raise TulpaError("tulpa service returned empty vacancy")

            return TulpaProtocol.TulpaVacancy(
                title=grpc_response.vacancy.title,
                description=grpc_response.vacancy.description,
                specialization=grpc_response.vacancy.specialization,
                city=grpc_response.vacancy.city,
                country=grpc_response.vacancy.country,
                salary_min=grpc_response.vacancy.salary_min,
                salary_max=grpc_response.vacancy.salary_max,
                salary_currency=grpc_response.vacancy.salary_currency,
                employment=_map_employment(grpc_response.vacancy.employment),
                work_format=_map_work_format(grpc_response.vacancy.work_format),
                is_internship=grpc_response.vacancy.is_internship,
                is_temporary_hiring=grpc_response.vacancy.is_temporary_hiring,
                possible_schedules=[
                    _map_possible_schedule(schedule) for schedule in grpc_response.vacancy.possible_schedules
                ],
                daily_work_hours=grpc_response.vacancy.daily_work_hours,
                required_experience=_map_required_experience(grpc_response.vacancy.required_experience),
                key_skills=grpc_response.vacancy.key_skills,
            )

        except GRPCError as e:
            log.error("failed to extract vacancy from raw with tulpa service", err=e)
            raise TulpaGRPCError.from_grpc(e) from e
        except Exception as e:
            log.error("failed to extract vacancy from raw with tulpa service", err=e)
            raise TulpaError("failed to extract vacancy from raw") from e

    @span(op="tulpa_adapter", name="push_analyse_candidate_task")
    @override
    async def push_analyse_candidate_task(
        self, request: TulpaProtocol.AnalyseCandidateRequest
    ) -> TulpaProtocol.AnalyseCandidateResponse:
        try:
            grpc_request = AnalyseCandidateAgainstCriteriaRequest(
                resume=request.resume_text,
                criteria=[
                    AnalyseCandidateAgainstCriteriaRequestCriterion(
                        id=c.id,
                        value=c.value,
                    )
                    for c in request.factors
                ],
                metadata=Struct.from_dict(request.metadata),
            )

            grpc_response = await self._dstub.analyse_candidate_against_criteria(grpc_request)

            if grpc_response.message_id == "":
                raise TulpaError("tulpa service returned empty message id")

            return TulpaProtocol.AnalyseCandidateResponse(task_id=grpc_response.message_id)
        except GRPCError as e:
            log.error("failed to extract vacancy from raw with tulpa service", err=e)
            raise TulpaGRPCError.from_grpc(e) from e
        except Exception as e:
            log.error("failed to extract vacancy from raw with tulpa service", err=e)
            raise TulpaError("failed to extract vacancy from raw") from e

    @span(op="tulpa_adapter", name="extract_candidate_from_raw")
    @override
    async def extract_candidate_from_raw(
        self, request: TulpaProtocol.ExtractCandidateFromRawRequest
    ) -> TulpaProtocol.ExtractCandidateFromRawResponse:
        grpc_request = ExtractCandidateFromRawRequest(
            text=request.raw_text,
            metadata=Struct.from_dict(request.metadata),
        )

        try:
            grpc_response = await self._dstub.extract_candidate_from_raw(grpc_request)

            if grpc_response.message_id == "":
                raise TulpaError("tulpa service returned empty message id")

            return TulpaProtocol.ExtractCandidateFromRawResponse(task_id=grpc_response.message_id)
        except GRPCError as e:
            log.error("failed to extract candidate from raw with tulpa service", err=e)
            raise TulpaError("failed to extract candidate from raw") from e
        except Exception as e:
            log.error("failed to extract candidate from raw with tulpa service", err=e)
            raise TulpaError("failed to extract candidate from raw") from e


def _map_employment(employment: Employment) -> domain.WorkTypeEnum:
    if employment == Employment.FULL_TIME:
        return domain.WorkTypeEnum.FULL_TIME
    if employment == Employment.PART_TIME:
        return domain.WorkTypeEnum.PART_TIME
    if employment == Employment.PROJECT:
        return domain.WorkTypeEnum.PROJECT
    if employment == Employment.SHIFT:
        return domain.WorkTypeEnum.SHIFT

    return domain.WorkTypeEnum.FULL_TIME


def _map_work_format(work_format: WorkFormat) -> domain.WorkFormatEnum:
    if work_format == WorkFormat.OFFICE:
        return domain.WorkFormatEnum.OFFICE
    if work_format == WorkFormat.REMOTE:
        return domain.WorkFormatEnum.REMOTE
    if work_format == WorkFormat.HYBRID:
        return domain.WorkFormatEnum.HYBRID
    if work_format == WorkFormat.TRAVEL:
        return domain.WorkFormatEnum.TRAVEL

    return domain.WorkFormatEnum.OFFICE


def _map_possible_schedule(schedule: Schedule) -> domain.ScheduleEnum:
    if schedule == Schedule._6_1:
        return domain.ScheduleEnum.SCHEDULE_6_1
    if schedule == Schedule._5_2:
        return domain.ScheduleEnum.SCHEDULE_5_2
    if schedule == Schedule._4_3:
        return domain.ScheduleEnum.SCHEDULE_4_3
    if schedule == Schedule._3_3:
        return domain.ScheduleEnum.SCHEDULE_3_3
    if schedule == Schedule._3_2:
        return domain.ScheduleEnum.SCHEDULE_3_2
    if schedule == Schedule._2_2:
        return domain.ScheduleEnum.SCHEDULE_2_2
    if schedule == Schedule._2_1:
        return domain.ScheduleEnum.SCHEDULE_2_1
    if schedule == Schedule._1_1:
        return domain.ScheduleEnum.SCHEDULE_1_1
    return domain.ScheduleEnum.SCHEDULE_5_2


def _map_required_experience(experience: RequiredExperience) -> domain.ExperienceEnum:
    if experience == RequiredExperience._0:
        return domain.ExperienceEnum.EXP_0
    if experience == RequiredExperience._1_3:
        return domain.ExperienceEnum.EXP_1_3
    if experience == RequiredExperience._3_6:
        return domain.ExperienceEnum.EXP_3_6
    if experience == RequiredExperience._6_PLUS:
        return domain.ExperienceEnum.EXP_6_PLUS

    return domain.ExperienceEnum.EXP_0
