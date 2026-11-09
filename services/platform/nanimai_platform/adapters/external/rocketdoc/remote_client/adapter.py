from typing import final, override

import structlog
from grpclib.client import Channel
from grpclib.exceptions import GRPCError

from nanimai_platform.domain.candidate.candidate import CandidateSourceEnum, CriterionStatusEnum
from nanimai_platform.external_clients.rocketdoc_api.resume.v1 import (
    CriteriaStatus,
    DownloadResumeRequest,
    GenerateResumeRequest,
    GenerateResumeRequestCriteria,
    GenerateResumeRequestStopFactors,
    ResumeServiceStub,
    Source,
)
from nanimai_platform.protocols.external.rocketdoc import RocketDocError, RocketDocProtocol
from nanimai_platform.utils import span

log = structlog.stdlib.get_logger("app.adapter.RocketDocAdapter")


@final
class GRPCRocketDocAdapter(RocketDocProtocol):
    def __init__(self, host: str, port: int):
        self._grpc_channel = Channel(host, port)
        self._stub = ResumeServiceStub(self._grpc_channel)

    async def close(self):
        self._grpc_channel.close()

    @span(op="rocketdoc_adapter", name="generate_resume")
    @override
    async def generate_resume(
        self, request: RocketDocProtocol.GenerateResumeRequest
    ) -> RocketDocProtocol.GenerateResumeResponse:
        try:
            grpc_request = GenerateResumeRequest(
                candidate_id=request.candidate_id,
                resume=request.resume,
                name=request.name,
                telephone_number=request.telephone_number or "",
                email=request.email or "",
                city=request.city or "",
                country=request.country or "",
                avatar=request.avatar or "",
                experience=request.experience or "",
                wanted_salary=request.wanted_salary or 0,
                budget=request.budget or 0,
                sub_specialisation=request.sub_specialisation,
                skills=request.skills,
                summary=request.summary,
                criteria=[
                    GenerateResumeRequestCriteria(
                        text=c.text,
                        max_score=c.max_score,
                        score=c.score,
                        score_percent=c.score_percent,
                        status={
                            CriterionStatusEnum.FULL: CriteriaStatus.STATUS_FULL,
                            CriterionStatusEnum.PARTIAL: CriteriaStatus.STATUS_PARTIAL,
                            CriterionStatusEnum.FAIL: CriteriaStatus.STATUS_REJECTED,
                            CriterionStatusEnum.UNKNOWN: CriteriaStatus.STATUS_NOT_FOUND,
                        }.get(c.status, CriteriaStatus.STATUS_UNSPECIFIED),
                    )
                    for c in request.criteria
                ],
                stop_factors=[
                    GenerateResumeRequestStopFactors(
                        text=sf.text,
                        penalty=sf.penalty,
                        is_present=sf.is_present,
                    )
                    for sf in request.stop_factors
                ],
                without_nanimai_attributes=request.without_nanimai_attributes,
                logo=request.logo or b"",
                logo_format=request.logo_format or "",
                main_color=request.main_color or "",
                total_score=request.score,
                vacancy_title=request.vacancy_title,
                source={
                    CandidateSourceEnum.HH: Source.HH,
                    CandidateSourceEnum.NANIMAI: Source.PDF,
                }.get(request.source, Source.PDF),
            )

            grpc_response = await self._stub.generate_resume(grpc_request)

            if grpc_response.error_message:
                log.error("rocketdoc service returned error", error=grpc_response.error_message)
                raise RocketDocError(f"rocketdoc service error: {grpc_response.error_message}")

            if not grpc_response.resume_id:
                raise RocketDocError("rocketdoc service returned empty resume_id")

            return RocketDocProtocol.GenerateResumeResponse(resume_id=grpc_response.resume_id)

        except GRPCError as e:
            log.error("failed to generate resume with rocketdoc service", err=e)
            raise RocketDocError("failed to generate resume") from e
        except RocketDocError:
            raise
        except Exception as e:
            log.error("failed to generate resume with rocketdoc service", err=e)
            raise RocketDocError("failed to generate resume") from e

    @span(op="rocketdoc_adapter", name="download_resume")
    @override
    async def download_resume(
        self, request: RocketDocProtocol.DownloadResumeRequest
    ) -> RocketDocProtocol.DownloadResumeResponse:
        try:
            grpc_request = DownloadResumeRequest(resume_id=request.resume_id)

            grpc_response = await self._stub.download_resume(grpc_request)

            if grpc_response.error_message:
                log.error("rocketdoc service returned error", error=grpc_response.error_message)
                raise RocketDocError(f"rocketdoc service error: {grpc_response.error_message}")

            if not grpc_response.link:
                raise RocketDocError("rocketdoc service returned empty link")

            return RocketDocProtocol.DownloadResumeResponse(link=grpc_response.link)

        except GRPCError as e:
            log.error("failed to download resume with rocketdoc service", err=e)
            raise RocketDocError("failed to download resume") from e
        except RocketDocError:
            raise
        except Exception as e:
            log.error("failed to download resume with rocketdoc service", err=e)
            raise RocketDocError("failed to download resume") from e
