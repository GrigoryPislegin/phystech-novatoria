from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from itertools import batched
from textwrap import dedent
from typing import Any, Literal, final

import ocrmypdf
import pdf4llm
import structlog
from pydantic_extra_types.currency_code import ISO4217 as CurrencyISO4217
from sqids import Sqids

from nanimai_platform import domain
from nanimai_platform.domain.candidate.candidate import CandidateAnalysisStatusEnum
from nanimai_platform.domain.scalar.scalars import UserID
from nanimai_platform.protocols.external.balance import (
    BalanceGRPCError,
    BalanceProtocol,
    ResourceOperationType,
)
from nanimai_platform.protocols.external.tulpa import (
    TulpaError,
    TulpaGRPCError,
    TulpaProtocol,
    TulpaValidateError,
)
from nanimai_platform.protocols.internal.repository.candidate import CandidateRepositoryProtocol
from nanimai_platform.services.candidate.factor_analysis_complete_hook import CandidateFactorAnalysisCompleteHook
from nanimai_platform.services.candidate.service import CandidateService
from nanimai_platform.services.criterion import CriterionService
from nanimai_platform.services.operation import OperationService
from nanimai_platform.services.stop_factor import StopFactorService
from nanimai_platform.services.vacancy.service import VacancyService
from nanimai_platform.utils.logging_span import span
from nanimai_platform.utils.map_grpc_error import AdvancedGRPCError
from nanimai_platform.utils.update_value import UpdateValue


class LLMServiceError(Exception): ...


class LLMServiceTargetNotFoundError(LLMServiceError): ...


class LLMServiceOperationCreationError(LLMServiceError): ...


class LLMServiceJobQueueError(LLMServiceError): ...


class LLMServiceTariffError(LLMServiceError): ...


class LLMServiceTulpaGRPCError(AdvancedGRPCError): ...


class LLMServiceBalanceGRPCError(AdvancedGRPCError): ...


log = structlog.stdlib.get_logger("app.service.LLMService")

slug_gen = Sqids(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_length=8)


@final
class LLMService:
    def __init__(
        self,
        tulpa_adapter: TulpaProtocol,
        criteria_service: CriterionService,
        stop_factors_service: StopFactorService,
        operation_service: OperationService,
        balance_adapter: BalanceProtocol,
        candidate_service: CandidateService,
        vacancy_service: VacancyService,
        candidate_repo: CandidateRepositoryProtocol,
        candidate_factor_analysis_complete_hook: CandidateFactorAnalysisCompleteHook,
    ):
        self._tulpa_adapter = tulpa_adapter
        self._criteria = criteria_service
        self._stop_factors = stop_factors_service
        self._operation_service = operation_service
        self._balance_adapter = balance_adapter
        self._candidate_service = candidate_service
        self._vacancy_service = vacancy_service
        self._candidate_repo = candidate_repo
        self._candidate_factor_analysis_complete_hook = candidate_factor_analysis_complete_hook

    @dataclass
    class NewAnalyzeOperationRequest:
        user_id: UserID
        candidate_id: domain.CandidateID
        vacancy_id: domain.VacancyID

    @span(op="operation_service", name="new_analyze_operation")
    async def new_analyze_operation(self, request: NewAnalyzeOperationRequest) -> domain.OperationID:
        try:
            log.info("reading candidate", candidate_id=request.candidate_id)
            candidate = await self._candidate_service.read(
                CandidateService.ReadCandidateRequest(id=request.candidate_id)
            )

            _ = await self._candidate_service.update(
                self._candidate_service.UpdateCandidateRequest(
                    id=request.candidate_id,
                    analysis_status=UpdateValue(CandidateAnalysisStatusEnum.STARTED),
                )
            )

            log.info("reserve resources", candidate_id=request.candidate_id, vacancy_id=request.vacancy_id)
            try:
                balance_response = await self._balance_adapter.reserve_resources(
                    BalanceProtocol.ReserveResourcesRequest(
                        user_id=str(request.user_id),
                        resource_id=str(request.vacancy_id),
                        operation=ResourceOperationType.RESUME_SCORING,
                        timeout=timedelta(minutes=10),
                    )
                )
            except BalanceGRPCError as e:
                log.error("Failed to reserve resources due to grpc error", err=e)
                raise LLMServiceBalanceGRPCError.from_adv(e) from e
            except Exception as e:
                log.error("Failed to reserve resources", err=e)
                raise LLMServiceTariffError("Failed to reserve resources") from e

            log.info("read criteria", candidate_id=request.candidate_id, vacancy_id=request.vacancy_id)
            criteria = await self._criteria.read_many_by_vacancy(
                self._criteria.ReadManyCriteriaByVacancyRequest(
                    vacancy_id=request.vacancy_id,
                )
            )

            log.info("read stop factors", candidate_id=request.candidate_id, vacancy_id=request.vacancy_id)
            stop_factors = await self._stop_factors.read_many_by_vacancy(
                self._stop_factors.ReadManyStopFactorsByVacancyRequest(
                    vacancy_id=request.vacancy_id,
                )
            )

            log.info("create generate analysis operation", candidate_id=request.candidate_id)
            new_operation = await self._operation_service.create_generate_analysis(
                self._operation_service.CreateGenerateAnalysisOperationRequest(
                    candidate_id=request.candidate_id,
                    finished_at=None,
                    status=domain.OperationStatus.RUNNING,
                    usage=[],
                    created_analysis_id=None,
                )
            )

            log.info("generate tulpa criteria", candidate_id=request.candidate_id)
            factors: list[TulpaProtocol.AnalysecandidateFactor] = []
            for criterion in criteria:
                factors.append(
                    TulpaProtocol.AnalysecandidateFactor(
                        id=f"candidate_id:{request.candidate_id}:criteria_id:{criterion.id}",
                        value=criterion.criterion,
                    )
                )

            for stop_factor in stop_factors:
                factors.append(
                    TulpaProtocol.AnalysecandidateFactor(
                        id=f"candidate_id:{request.candidate_id}:stop_factor_id:{stop_factor.id}",
                        value=stop_factor.stop_factor,
                    )
                )

            meta = {
                "candidate_id": str(request.candidate_id),
                "vacancy_id": str(request.vacancy_id),
                "operation_id": str(new_operation.id),
                "transaction_id": balance_response.reservation_id,
            }

            log.info("generate tulpa request", candidate_id=request.candidate_id)
            tulpa_request = TulpaProtocol.AnalyseCandidateRequest(
                resume_text=self.__candidate_to_string(candidate),
                factors=factors,
                metadata=meta,
            )

            _ = await self._tulpa_adapter.push_analyse_candidate_task(tulpa_request)
            log.info("pushed analyze candidate task", candidate_id=request.candidate_id)

            return new_operation.id
        except LLMServiceTariffError as e:
            log.error("Failed to reserve resources", err=e)
            _ = await self._candidate_service.update(
                self._candidate_service.UpdateCandidateRequest(
                    id=request.candidate_id,
                    analysis_status=UpdateValue(CandidateAnalysisStatusEnum.REJECTED),
                )
            )
            raise e
        except LLMServiceBalanceGRPCError as e:
            log.error("Failed to reserve resources", err=e)
            _ = await self._candidate_service.update(
                self._candidate_service.UpdateCandidateRequest(
                    id=request.candidate_id,
                    analysis_status=UpdateValue(CandidateAnalysisStatusEnum.REJECTED),
                )
            )
            raise e
        except LLMServiceError as e:
            _ = await self._candidate_service.update(
                self._candidate_service.UpdateCandidateRequest(
                    id=request.candidate_id,
                    analysis_status=UpdateValue(CandidateAnalysisStatusEnum.FAILED),
                )
            )
            raise e
        except TulpaGRPCError as e:
            _ = await self._candidate_service.update(
                self._candidate_service.UpdateCandidateRequest(
                    id=request.candidate_id,
                    analysis_status=UpdateValue(CandidateAnalysisStatusEnum.FAILED),
                )
            )
            log.error("Failed to start analyze operation due to tulpa error", err=e)
            raise LLMServiceTulpaGRPCError.from_adv(e) from e
        except Exception as e:
            _ = await self._candidate_service.update(
                self._candidate_service.UpdateCandidateRequest(
                    id=request.candidate_id,
                    analysis_status=UpdateValue(CandidateAnalysisStatusEnum.FAILED),
                )
            )
            # todo: better error handling
            log.error("Failed to start analyze operation", err=e)
            raise LLMServiceError("LLM service error") from e

    @dataclass
    class FinishAnalyseResult:
        factor_id: str
        status: domain.CriterionStatusEnum
        resume_summary: str

    @dataclass
    class FinishAnalyseOperationRequest:
        status: Literal["success", "error"]
        metadata: dict[str, Any]
        results: list[LLMService.FinishAnalyseResult]
        error: str | None = None

    async def finish_analyse_operation(self, request: FinishAnalyseOperationRequest) -> None:  # noqa: C901
        log.info("finish analyze operation", request=request)

        try:
            if "transaction_id" not in request.metadata:
                raise LLMServiceError("transaction_id not found in metadata")
            if "operation_id" not in request.metadata:
                raise LLMServiceError("operation_id not found in metadata")
            if "candidate_id" not in request.metadata:
                raise LLMServiceError("candidate_id not found in metadata")

            candidate_id = domain.CandidateID(request.metadata["candidate_id"])

            if request.status == "error":
                await self._balance_adapter.cancel_reservation(
                    BalanceProtocol.CancelReservationRequest(
                        reservation_id=request.metadata["transaction_id"],
                    )
                )
            else:
                await self._balance_adapter.confirm_reservation(
                    BalanceProtocol.ConfirmReservationRequest(
                        reservation_id=request.metadata["transaction_id"],
                    )
                )

            _ = await self._operation_service.update_generate_analysis(
                self._operation_service.UpdateGenerateAnalysisOperationRequest(
                    id=domain.OperationID(request.metadata["operation_id"]),
                    finished_at=datetime.now(UTC),
                    status=domain.OperationStatus.FINISHED
                    if request.status == "success"
                    else domain.OperationStatus.FAILED,
                    usage=[],
                    created_analysis_id=None,
                )
            )

            criteria_updates = CandidateService.SetCandidateCriteriaRequest(id=candidate_id, updates=[])
            stop_factors_updates = CandidateService.SetCandidateStopFactorsRequest(id=candidate_id, updates=[])

            for result in request.results:
                _, _, what, id = result.factor_id.split(":")
                log.debug("updating factor", what=what, id=id)
                if what == "criteria_id":
                    criteria_updates.updates.append(
                        self._candidate_service.SetCandidateCriterionRequest(
                            criterion_id=domain.CriterionID(id),
                            score=UpdateValue(1)
                            if result.status == domain.CriterionStatusEnum.FULL
                            else UpdateValue(0.5)
                            if result.status == domain.CriterionStatusEnum.PARTIAL
                            else UpdateValue(0),
                            status=UpdateValue(result.status),
                            description=UpdateValue(result.resume_summary),
                        )
                    )
                elif what == "stop_factor_id":
                    stop_factors_updates.updates.append(
                        self._candidate_service.SetCandidateStopFactorRequest(
                            stop_factor_id=domain.StopFactorID(id),
                            status=UpdateValue(result.status == domain.CriterionStatusEnum.FULL),
                            description=UpdateValue(result.resume_summary),
                        )
                    )

            log.info(f"form {len(criteria_updates.updates) + len(stop_factors_updates.updates)} updates")

            _ = await self._candidate_service.set_candidate_criteria(criteria_updates)
            _ = await self._candidate_service.set_candidate_stop_factors(stop_factors_updates)

            # read raw from database
            candidate = await self._candidate_repo.read_candidate(
                CandidateRepositoryProtocol.ReadCandidateRequest(id=candidate_id)
            )

            if criteria_updates or stop_factors_updates:
                _ = await self._candidate_factor_analysis_complete_hook.factor_analysis_complete(
                    self._candidate_factor_analysis_complete_hook.FactorAnalysisCompleteRequest(candidate=candidate)
                )

            _ = await self._candidate_service.update(
                self._candidate_service.UpdateCandidateRequest(
                    id=candidate_id,
                    analysis_status=UpdateValue(
                        CandidateAnalysisStatusEnum.SUCCESS
                        if request.status == "success"
                        else CandidateAnalysisStatusEnum.FAILED
                    ),
                )
            )
        except Exception as e:
            _ = await self._candidate_service.update(
                self._candidate_service.UpdateCandidateRequest(
                    id=domain.CandidateID(request.metadata["candidate_id"]),
                    analysis_status=UpdateValue(CandidateAnalysisStatusEnum.FAILED),
                )
            )
            # todo: better error handling
            log.error("Failed to finish analyze operation", err=e)
            raise LLMServiceError("LLM service error") from e

    @dataclass
    class GenerateVacancyCriteriaRequest:
        user_id: domain.UserID
        project_id: domain.ProjectID
        title: str
        description: str
        specialization: str
        status: domain.VacancyStatus | None = None
        city: str | None = None
        country: str | None = None
        hire_amount: int | None = None
        salary: domain.SalaryAmountRange | None = None
        work_type: domain.WorkTypeEnum | None = None
        work_format: list[domain.WorkFormatEnum] | None = None
        is_internship: bool | None = None
        is_temphire: bool | None = None
        schedule: list[domain.ScheduleEnum] | None = None
        daily_rate: list[int] | None = None
        experience: domain.ExperienceEnum | None = None
        skills: list[domain.Skill] | None = None
        stages: list[domain.VacancyStageStatus] | None = None
        publication: domain.VacancyPublication | None = None

    @span(op="llm_service", name="generate_vacancy_criteria")
    async def generate_vacancy_criteria(self, request: GenerateVacancyCriteriaRequest) -> list[domain.CriterionPayload]:
        try:
            tulpa_request = TulpaProtocol.GenerateVacancyCriteriaRequest(
                full_text=self.__vacancy_to_string(
                    title=request.title,
                    specialization=request.specialization,
                    city=request.city,
                    country=request.country,
                    salary=request.salary,
                    description=request.description,
                    work_format=", ".join(w.value for w in request.work_format) if request.work_format else None,
                    work_type=request.work_type.value if request.work_type else None,
                    schedule=", ".join(s.value for s in request.schedule) if request.schedule else None,
                    daily_rate=", ".join(str(d) for d in request.daily_rate) if request.daily_rate else None,
                    skills=[s.title for s in request.skills] if request.skills else None,
                ),
                nessesary_weight=8,
                beneficial_weight=4,
                optional_weight=2,
            )
            tulpa_response = await self._tulpa_adapter.generate_vacancy_criteria(tulpa_request)

            criteria: list[domain.CriterionPayload] = []
            for tulpa_criterion in tulpa_response.criteria:
                criteria.append(
                    domain.CriterionPayload(
                        criterion=tulpa_criterion.criterion,
                        initial_weight=tulpa_criterion.initial_weight,
                    )
                )
            return criteria
        except TulpaValidateError as e:
            log.error(f"Invalid data from tulpa service: {e}")
            raise LLMServiceError("invalid data from tulpa service") from e
        except TulpaGRPCError as e:
            log.error("Failed to generate vacancy criteria due to tulpa error", err=e)
            raise LLMServiceTulpaGRPCError.from_adv(e) from e
        except TulpaError as e:
            log.error(f"Failed to generate vacancy criteria with tulpa service: {e}")
            raise LLMServiceError("failed to generate vacancy criteria with tulpa service") from e
        except Exception as e:
            log.error(f"LLM service error: {e}")
            raise LLMServiceError("LLM service error") from e

    @dataclass
    class ParseVacancyRequest:
        user_id: domain.UserID
        project_id: domain.ProjectID
        file: bytes

    @span(op="llm_service", name="parse_vacancy")
    async def parse_vacancy(self, request: ParseVacancyRequest) -> domain.Vacancy:
        try:
            raw_text = self._process_pdf(request.file)
            vacancy = await self._tulpa_adapter.extract_vacancy_from_raw(raw_text)
            return domain.Vacancy(
                id=domain.VacancyID(),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                deleted_at=None,
                user_id=request.user_id,
                project_id=request.project_id,
                title=vacancy.title,
                description=vacancy.description,
                specialization=vacancy.specialization,
                thumbnail_url="",
                status=domain.VacancyStatus.OPEN,
                city=vacancy.city,
                country=vacancy.country,
                hire_amount=None,
                salary=domain.SalaryAmountRange(
                    currency=CurrencyISO4217(vacancy.salary_currency or "RUB"),
                    min=vacancy.salary_min,
                    max=vacancy.salary_max,
                )
                if vacancy.salary_min is not None and vacancy.salary_max is not None
                else None,
                work_type=vacancy.employment,
                work_format=[vacancy.work_format],
                is_internship=vacancy.is_internship,
                is_temphire=vacancy.is_temporary_hiring,
                schedule=vacancy.possible_schedules,
                daily_rate=vacancy.daily_work_hours,
                experience=vacancy.required_experience,
                skills=[domain.Skill(title=skill) for skill in vacancy.key_skills],
                stages=[
                    domain.VacancyStageStatus(stage=domain.VacancyStageEnum.REJECTED_USER, shown=True),
                    domain.VacancyStageStatus(stage=domain.VacancyStageEnum.REJECTED_AI, shown=True),
                    domain.VacancyStageStatus(stage=domain.VacancyStageEnum.MAGIC_AI, shown=True),
                    domain.VacancyStageStatus(stage=domain.VacancyStageEnum.SELECTED_AI, shown=True),
                    domain.VacancyStageStatus(stage=domain.VacancyStageEnum.SELECTED_USER, shown=True),
                    domain.VacancyStageStatus(stage=domain.VacancyStageEnum.MESSAGE, shown=True),
                    domain.VacancyStageStatus(stage=domain.VacancyStageEnum.PRELIMINARY_CALL, shown=True),
                    domain.VacancyStageStatus(stage=domain.VacancyStageEnum.INTERVIEW, shown=True),
                    domain.VacancyStageStatus(stage=domain.VacancyStageEnum.TEST_TASK, shown=True),
                    domain.VacancyStageStatus(stage=domain.VacancyStageEnum.FINAL_TEST, shown=True),
                    domain.VacancyStageStatus(stage=domain.VacancyStageEnum.OFFER, shown=True),
                    domain.VacancyStageStatus(stage=domain.VacancyStageEnum.ACCEPTED, shown=True),
                ],
                publication=domain.VacancyPublication(
                    hh=domain.PublicationStatus(
                        state=domain.PublicationStatusEnum.NOT_PUBLISHED, url=None, publication_id=None
                    ),
                    avito=domain.PublicationStatus(
                        state=domain.PublicationStatusEnum.NOT_PUBLISHED, url=None, publication_id=None
                    ),
                ),
                statistics=domain.VacancyStatistics(
                    total_candidates=0,
                    platform_candidates=0,
                    delegated_candidates=0,
                ),
                threshold=0,
            )

        except TulpaGRPCError as e:
            log.error("Failed to generate vacancy criteria due to tulpa error", err=e)
            raise LLMServiceTulpaGRPCError.from_adv(e) from e

    @dataclass
    class ParseCandidateRequest:
        user_id: domain.UserID
        vacancy_id: domain.VacancyID
        file: bytes

    @span(op="llm_service", name="parse_candidate")
    async def parse_candidate(self, request: ParseCandidateRequest) -> domain.OperationID:
        """Parse candidate from PDF file and return task ID for tracking.

        Returns:
            str: Task ID from Tulpa service for tracking the parsing operation
        """

        vacancy = await self._vacancy_service.read(VacancyService.ReadVacancyRequest(id=request.vacancy_id))
        raw_text = self._process_pdf(request.file)

        log.info("create parse candidate operation", vacancy_id=request.vacancy_id)
        new_operation = await self._operation_service.create_parse_candidate(
            self._operation_service.CreateParseCandidateOperationRequest(
                vacancy_id=request.vacancy_id,
                filepath="",
                finished_at=None,
                status=domain.OperationStatus.RUNNING,
                usage=[],
                created_candidate_id=None,
            )
        )

        metadata = {
            "user_id": str(request.user_id),
            "project_id": str(vacancy.project_id),
            "vacancy_id": str(request.vacancy_id),
            "operation_id": str(new_operation.id),
        }

        _ = await self._tulpa_adapter.extract_candidate_from_raw(
            self._tulpa_adapter.ExtractCandidateFromRawRequest(
                raw_text=raw_text,
                metadata=metadata,
            )
        )

        return new_operation.id

    @dataclass
    class FinishParseCandidateRequest:
        status: Literal["success", "error"]
        metadata: dict[str, str]
        candidate_data: TulpaProtocol.TulpaCandidate | None = None
        error: str | None = None

    @span(op="llm_service", name="finish_parse_candidate")
    async def finish_parse_candidate(self, request: FinishParseCandidateRequest) -> domain.Candidate | None:  # noqa: C901
        try:
            log.info("finish parse candidate operation", request=request)

            if "operation_id" not in request.metadata:
                raise LLMServiceError("operation_id not found in metadata")
            if "vacancy_id" not in request.metadata:
                raise LLMServiceError("vacancy_id not found in metadata")
            if "user_id" not in request.metadata:
                raise LLMServiceError("user_id not found in metadata")
            if "project_id" not in request.metadata:
                raise LLMServiceError("project_id not found in metadata")

            created_candidate: domain.Candidate | None = None

            if not (request.status == "success" and request.candidate_data is not None):
                # Handle error case
                log.warning("parse candidate failed", error=request.error)
                _ = await self._operation_service.update_parse_candidate(
                    self._operation_service.UpdateParseCandidateOperationRequest(
                        id=domain.OperationID(request.metadata["operation_id"]),
                        finished_at=datetime.now(UTC),
                        status=domain.OperationStatus.FAILED,
                        usage=[],
                        created_candidate_id=None,
                    )
                )
                return None

            # Create new candidate from parsed data
            log.info("creating candidate from parsed data")

            # Calculate total experience in months
            experience_months = request.candidate_data.experience_years * 12 + request.candidate_data.experience_months

            # Prepare expected salary
            expected_salary = None
            if request.candidate_data.expected_salary is not None and request.candidate_data.expected_salary > 0:
                expected_salary = domain.ExpectedSalary(
                    currency=CurrencyISO4217("RUB"),
                    value=request.candidate_data.expected_salary,
                )

            # Prepare skills
            skills = [domain.Skill(title=skill) for skill in request.candidate_data.skills]

            slug = slug_gen.encode(
                list(map(sum, batched(list(sha256(request.candidate_data.resume.encode("utf-8")).digest()), 16)))
            )[:10].upper()

            # Create candidate
            created_candidate = await self._candidate_service.create(
                self._candidate_service.CreateCandidateRequest(
                    user_id=domain.UserID(request.metadata["user_id"]),
                    project_id=domain.ProjectID(request.metadata["project_id"]),
                    vacancy_id=domain.VacancyID(request.metadata["vacancy_id"]),
                    name=request.candidate_data.name or f"Кандидат {slug}",
                    phone_number=request.candidate_data.phone_number,
                    email=request.candidate_data.email,
                    city=request.candidate_data.city,
                    country=request.candidate_data.country,
                    experience=experience_months,
                    expected_salary=expected_salary,
                    skills=skills,
                    resume=request.candidate_data.resume,
                    notes="",
                    source=domain.CandidateSourceEnum.NANIMAI,
                    status=domain.VacancyStageEnum.MAGIC_AI,
                )
            )

            log.info("candidate created successfully", candidate_id=created_candidate.id)

            try:
                _ = await self._operation_service.update_parse_candidate(
                    self._operation_service.UpdateParseCandidateOperationRequest(
                        id=domain.OperationID(request.metadata["operation_id"]),
                        finished_at=datetime.now(UTC),
                        status=domain.OperationStatus.FINISHED,
                        usage=[],
                        created_candidate_id=created_candidate.id,
                    )
                )
            except Exception:
                log.error("failed to update parse candidate operation")

            try:
                _ = await self.new_analyze_operation(
                    self.NewAnalyzeOperationRequest(
                        user_id=domain.UserID(request.metadata["user_id"]),
                        vacancy_id=domain.VacancyID(request.metadata["vacancy_id"]),
                        candidate_id=created_candidate.id,
                    )
                )
            except Exception:
                log.error("failed to start new analyse operation for newly created candidate")
                pass

            return created_candidate

        except Exception as e:
            log.error("Failed to finish parse candidate operation", err=e)
            # Try to update operation to failed status
            try:
                _ = await self._operation_service.update_parse_candidate(
                    self._operation_service.UpdateParseCandidateOperationRequest(
                        id=domain.OperationID(request.metadata["operation_id"]),
                        finished_at=datetime.now(UTC),
                        status=domain.OperationStatus.FAILED,
                        usage=[],
                        created_candidate_id=None,
                    )
                )
            except Exception as inner_e:
                log.error("Failed to update operation to failed status", err=inner_e)
            raise LLMServiceError("LLM service error") from e

    def __vacancy_to_string(
        self,
        title: str,
        specialization: str,
        city: str | None,
        country: str | None,
        salary: domain.SalaryAmountRange | None,
        description: str,
        work_format: str | None,
        work_type: str | None,
        schedule: str | None,
        daily_rate: str | None,
        skills: list[str] | None,
    ) -> str:
        return dedent(f"""
        {title}
        Специализация: {specialization}
        Город: {city or "Не указано"}, Страна: {country or "Не указано"}

        Зарплата: {f"от {salary.min or 'Не указано'} до {salary.max or 'Не указано'}" if salary is not None else "Не указано"}

        Описание:
        {description}

        Формат работы: {work_format or "Не указано"}
        Тип работы: {work_type}
        Рабочий график: {schedule or "Не указано"}
        Рабочие часы: {daily_rate or "Не указано"}

        Требуемые навыки: {", ".join(skills) if skills else "Не указаны"}
        """)  # noqa: E501

    def _process_pdf(self, content: bytes) -> str:
        log.debug("processing pdf file")
        with tempfile.TemporaryDirectory() as tmp_dir:
            log.debug("creating temporary directory", tmp_dir=tmp_dir)
            path = f"{tmp_dir}/input.pdf"

            log.debug("writing pdf file to temporary directory", path=path)
            with open(path, "wb") as f:
                _ = f.write(content)

            log.debug("processing pdf file", path=path)
            text = pdf4llm.to_markdown(path, show_progress=False)

            if len(text) > 200:
                return text

            log.warn("Too small text, retrying with ocrmypdf to transform visual images to text")
            ocrmypdf.ocr(path, f"{tmp_dir}/output.pdf", deskew=True, language=["rus", "eng"], force_ocr=True)
            return pdf4llm.to_markdown(f"{tmp_dir}/output.pdf", show_progress=False)

    def __candidate_to_string(self, candidate: domain.Candidate):
        return dedent(f"""{candidate.name}
        {candidate.city or "Не указано"}, {candidate.country or "Не указано"}
        Ожилание по зарплате: {candidate.expected_salary.value if candidate.expected_salary else "Не указано"}{candidate.expected_salary.currency if candidate.expected_salary else ""}
        Список навыков: {", ".join(s.title for s in candidate.skills)}
        Опыт работы: {candidate.experience} месяцев
        Резюме: {candidate.resume}
        """)  # noqa: E501
