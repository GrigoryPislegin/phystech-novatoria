import math
from typing import TYPE_CHECKING, final

import structlog
from datauri import DataURI
from pydantic import BaseModel

from nanimai_platform.domain import CandidateID
from nanimai_platform.domain.candidate.candidate import Candidate, CriterionStatusEnum
from nanimai_platform.protocols.external.rocketdoc import RocketDocError, RocketDocProtocol, RocketDocValidateError
from nanimai_platform.services.candidate.service import CandidateService
from nanimai_platform.services.criterion.service import CriterionService
from nanimai_platform.services.project.service import ProjectService
from nanimai_platform.services.score_calculation.service import ScoreCalculationService
from nanimai_platform.services.stop_factor.service import StopFactorService
from nanimai_platform.services.thumbnail.service import ThumbnailService
from nanimai_platform.services.vacancy.service import VacancyService
from nanimai_platform.utils.experience_formatter import format_experience_months
from nanimai_platform.utils.logging_span import span

if TYPE_CHECKING:
    from nanimai_platform.infra.config import CDNConfig

log = structlog.stdlib.get_logger("app.service.ResumeDownloadService")


def true_round(value: float) -> int:
    if value - math.floor(value) < 0.5:
        return math.floor(value)

    return math.ceil(value)


class ResumeDownloadServiceError(Exception): ...


class ResumeDownloadServiceValidateError(Exception): ...


class ResumeDownloadServiceCandidateNotFoundError(Exception): ...


@final
class ResumeDownloadService:
    def __init__(
        self,
        rocketdoc_adapter: RocketDocProtocol,
        candidate: CandidateService,
        project: ProjectService,
        criterion: CriterionService,
        stop_factor: StopFactorService,
        vacancy: VacancyService,
        score: ScoreCalculationService,
        cdn_config: "CDNConfig",
        thumbnail: ThumbnailService,
    ):
        self._rocketdoc_adapter = rocketdoc_adapter
        self._candidate = candidate
        self._project = project
        self._criterion = criterion
        self._stop_factor = stop_factor
        self._vacancy = vacancy
        self._score = score
        self._cdn_config = cdn_config
        self._thumbnail = thumbnail

    class GenerateResumeRequest(BaseModel):
        candidate_id: CandidateID

    class GenerateResumeResponse(BaseModel):
        resume_id: str

    async def _prepare_criteria(self, candidate: Candidate) -> list[RocketDocProtocol.Criterion]:
        criteria: list[RocketDocProtocol.Criterion] = []
        if candidate.criteria:
            all_criteria = await self._criterion.read_many_by_vacancy(
                CriterionService.ReadManyCriteriaByVacancyRequest(vacancy_id=candidate.vacancy_id)
            )
            criteria_map = {c.id: c for c in all_criteria}
            total_score = sum(criterion_entity.initial_weight for criterion_entity in all_criteria)

            for criterion_id, criterion_analysis in candidate.criteria.items():
                if criterion_analysis.score is not None:
                    if criterion_entity := criteria_map.get(criterion_id):
                        criteria.append(
                            RocketDocProtocol.Criterion(
                                text=criterion_entity.criterion,
                                max_score=criterion_entity.initial_weight,
                                score=true_round(criterion_analysis.score * criterion_entity.initial_weight),
                                status=criterion_analysis.status or CriterionStatusEnum.UNKNOWN,
                                score_percent=true_round(
                                    (criterion_analysis.score * criterion_entity.initial_weight) / total_score * 100
                                ),
                            )
                        )
        return criteria

    async def _prepare_stop_factors(self, candidate: Candidate) -> list[RocketDocProtocol.StopFactor]:
        stop_factors: list[RocketDocProtocol.StopFactor] = []
        if candidate.stop_factors:
            all_stop_factors = await self._stop_factor.read_many_by_vacancy(
                StopFactorService.ReadManyStopFactorsByVacancyRequest(vacancy_id=candidate.vacancy_id)
            )
            stop_factors_map = {sf.id: sf for sf in all_stop_factors}

            for stop_factor_id, stop_factor_analysis in candidate.stop_factors.items():
                if stop_factor_entity := stop_factors_map.get(stop_factor_id):
                    penalty = 0
                    if stop_factor_analysis.status is True:
                        penalty = stop_factor_entity.initial_weight
                    stop_factors.append(
                        RocketDocProtocol.StopFactor(
                            text=stop_factor_entity.stop_factor,
                            penalty=penalty,
                            is_present=stop_factor_analysis.status or False,
                        )
                    )
        return stop_factors

    @span(op="resume_download_service", name="generate_resume")
    async def generate_resume(self, request: GenerateResumeRequest) -> GenerateResumeResponse:  # noqa: C901
        try:
            candidate = await self._candidate.read(CandidateService.ReadCandidateRequest(id=request.candidate_id))
            vacancy = await self._vacancy.read(VacancyService.ReadVacancyRequest(id=candidate.vacancy_id))
            template_settings = await self._project.get_project_settings(
                ProjectService.GetProjectSettingsRequest(id=candidate.project_id)
            )
            criteria = await self._prepare_criteria(candidate)
            stop_factors = await self._prepare_stop_factors(candidate)

            avatar_url = f"{self._cdn_config.base_url}/{candidate.thumbnail_url}" if candidate.thumbnail_url else None
            if template_settings.main_color:
                avatar_path = await self._thumbnail.create_candidate_thumbnail(
                    candidate.name, main_color=template_settings.main_color
                )
                avatar_url = f"{self._cdn_config.base_url}/{avatar_path}"
            experience_text = format_experience_months(candidate.experience) if candidate.experience else None

            score_result = await self._score.calculate_candidate_score(
                ScoreCalculationService.CalculateCandidateScoreRequest(candidate_id=candidate.id)
            )
            score = true_round(score_result.score * 100)

            logo_bytes = None
            if template_settings.logo_data_uri:
                try:
                    logo_bytes = DataURI(template_settings.logo_data_uri).data
                except Exception as e:
                    log.error("failed to decode base64 logo", err=e)

            rocketdoc_request = RocketDocProtocol.GenerateResumeRequest(
                candidate_id=str(candidate.id),
                resume=candidate.resume,
                name=candidate.name,
                telephone_number=candidate.phone_number,
                email=candidate.email,
                city=candidate.city,
                country=candidate.country,
                avatar=avatar_url,
                experience=experience_text,
                wanted_salary=candidate.expected_salary.value if candidate.expected_salary else None,
                budget=vacancy.salary.max if vacancy.salary else None,
                sub_specialisation=[vacancy.specialization],
                skills=[skill.title for skill in candidate.skills],
                summary=[],
                criteria=criteria,
                stop_factors=stop_factors,
                without_nanimai_attributes=template_settings.without_nanimai_attributes,
                logo=logo_bytes,
                logo_format=template_settings.logo_format,
                main_color=template_settings.main_color,
                score=score,
                vacancy_title=vacancy.title,
                source=candidate.source,
            )

            response = await self._rocketdoc_adapter.generate_resume(rocketdoc_request)

            return self.GenerateResumeResponse(resume_id=response.resume_id)

        except RocketDocValidateError as e:
            log.error("failed to generate resume due to validation error", err=e)
            raise ResumeDownloadServiceValidateError("validation error") from e
        except RocketDocError as e:
            log.error("failed to generate resume", err=e)
            raise ResumeDownloadServiceError("failed to generate resume") from e
        except Exception as e:
            log.error("failed to generate resume", err=e)
            raise ResumeDownloadServiceError("unknown error") from e

    class DownloadResumeRequest(BaseModel):
        resume_id: str

    class DownloadResumeResponse(BaseModel):
        download_link: str

    @span(op="resume_download_service", name="download_resume")
    async def download_resume(self, request: DownloadResumeRequest) -> DownloadResumeResponse:
        try:
            rocketdoc_request = RocketDocProtocol.DownloadResumeRequest(resume_id=request.resume_id)

            response = await self._rocketdoc_adapter.download_resume(rocketdoc_request)

            return self.DownloadResumeResponse(download_link=response.link)

        except RocketDocValidateError as e:
            log.error("failed to download resume due to validation error", err=e)
            raise ResumeDownloadServiceValidateError("validation error") from e
        except RocketDocError as e:
            log.error("failed to download resume", err=e)
            raise ResumeDownloadServiceError("failed to download resume") from e
        except Exception as e:
            log.error("failed to download resume", err=e)
            raise ResumeDownloadServiceError("unknown error") from e

    class GetResumeDownloadLinkRequest(BaseModel):
        candidate_id: CandidateID

    class GetResumeDownloadLinkResponse(BaseModel):
        download_link: str

    @span(op="resume_download_service", name="get_resume_download_link")
    async def get_resume_download_link(self, request: GetResumeDownloadLinkRequest) -> GetResumeDownloadLinkResponse:
        try:
            generate_response = await self.generate_resume(
                self.GenerateResumeRequest(
                    candidate_id=request.candidate_id,
                )
            )

            download_response = await self.download_resume(
                self.DownloadResumeRequest(resume_id=generate_response.resume_id)
            )

            return self.GetResumeDownloadLinkResponse(download_link=download_response.download_link)

        except ResumeDownloadServiceValidateError:
            raise
        except ResumeDownloadServiceError:
            raise
        except Exception as e:
            log.error("failed to get resume download link", err=e)
            raise ResumeDownloadServiceError("unknown error") from e
