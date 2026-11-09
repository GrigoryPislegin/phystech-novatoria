from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from nanimai_platform.domain.candidate.candidate import CandidateSourceEnum, CriterionStatusEnum


class RocketDocError(Exception): ...


class RocketDocValidateError(Exception): ...


class RocketDocProtocol(ABC):
    class Criterion(BaseModel):
        text: str
        max_score: int
        score: int
        score_percent: int
        status: CriterionStatusEnum

    class StopFactor(BaseModel):
        text: str
        penalty: int
        is_present: bool

    class GenerateResumeRequest(BaseModel):
        candidate_id: str
        resume: str
        name: str
        telephone_number: str | None = None
        email: str | None = None
        city: str | None = None
        country: str | None = None
        avatar: str | None = None
        experience: str | None = None
        wanted_salary: int | None = None
        budget: int | None = None
        sub_specialisation: list[str] = []
        skills: list[str] = []
        summary: list[str] = []
        criteria: list[RocketDocProtocol.Criterion] = []
        stop_factors: list[RocketDocProtocol.StopFactor] = []
        without_nanimai_attributes: bool = False
        logo: bytes | None = None
        logo_format: str | None = None
        main_color: str | None = None
        score: int
        vacancy_title: str
        source: CandidateSourceEnum

    class GenerateResumeResponse(BaseModel):
        resume_id: str

    @abstractmethod
    async def generate_resume(self, request: GenerateResumeRequest) -> GenerateResumeResponse: ...

    class DownloadResumeRequest(BaseModel):
        resume_id: str

    class DownloadResumeResponse(BaseModel):
        link: str

    @abstractmethod
    async def download_resume(self, request: DownloadResumeRequest) -> DownloadResumeResponse: ...
