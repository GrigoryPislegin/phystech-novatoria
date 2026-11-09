from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

import nanimai_platform.domain as domain
from nanimai_platform.utils.map_grpc_error import AdvancedGRPCError


class TulpaError(Exception): ...


class TulpaValidateError(Exception): ...


class TulpaGRPCError(AdvancedGRPCError): ...


class TulpaProtocol(ABC):
    class GenerateVacancyCriteriaRequest(BaseModel):
        full_text: str
        nessesary_weight: int = Field(default=8)
        beneficial_weight: int = Field(default=4)
        optional_weight: int = Field(default=2)

    class TulpaCriterion(BaseModel):
        criterion: str
        initial_weight: int

    class TulpaCandidate(BaseModel):
        name: str | None
        city: str | None
        country: str | None
        phone_number: str | None
        email: str | None
        experience_years: int
        experience_months: int
        expected_salary: int | None
        skills: list[str]
        resume: str

    class GenerateVacancyCriteriaResponse(BaseModel):
        criteria: list[TulpaProtocol.TulpaCriterion]

    @abstractmethod
    async def generate_vacancy_criteria(
        self, request: GenerateVacancyCriteriaRequest
    ) -> GenerateVacancyCriteriaResponse:
        """Generates vacancy criteria using Tulpa service.

        Raises:
            TulpaValidateError - wrong data error
            TulpaError - unexpected error
            TulpaGRPCError - GRPC error
        Returns:
            GenerateVacancyCriteriaResponse - generated criteria
        """
        ...

    class TulpaVacancy(BaseModel):
        title: str
        description: str
        specialization: str
        city: str | None
        country: str | None
        salary_min: int | None
        salary_max: int | None
        salary_currency: str | None
        employment: domain.WorkTypeEnum
        work_format: domain.WorkFormatEnum
        is_internship: bool
        is_temporary_hiring: bool
        possible_schedules: list[domain.ScheduleEnum]
        daily_work_hours: list[int]
        required_experience: domain.ExperienceEnum
        key_skills: list[str]

    @abstractmethod
    async def extract_vacancy_from_raw(self, raw_text: str) -> TulpaVacancy: ...

    class AnalysecandidateFactor(BaseModel):
        id: str
        value: str

    class AnalyseCandidateRequest(BaseModel):
        resume_text: str
        factors: list[TulpaProtocol.AnalysecandidateFactor]
        metadata: dict[str, Any]

    class AnalyseCandidateResponse(BaseModel):
        task_id: str

    @abstractmethod
    async def push_analyse_candidate_task(self, request: AnalyseCandidateRequest) -> AnalyseCandidateResponse: ...

    class ExtractCandidateFromRawRequest(BaseModel):
        raw_text: str
        metadata: dict[str, Any]

    class ExtractCandidateFromRawResponse(BaseModel):
        task_id: str

    @abstractmethod
    async def extract_candidate_from_raw(
        self, request: ExtractCandidateFromRawRequest
    ) -> ExtractCandidateFromRawResponse:
        """Extracts structured candidate information from raw text.

        Raises:
            TulpaValidateError - wrong data error
            TulpaError - unexpected error
        Returns:
            ExtractCandidateFromRawResponse - task id for tracking
        """
        ...
