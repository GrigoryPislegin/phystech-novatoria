from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic_core import Url

from nanimai_platform.domain.candidate.candidate import (
    Candidate,
    CandidateAnalysisStatusEnum,
    CandidateCard,
    CandidateSourceEnum,
    ContactTypeEnum,
    CriterionAnalysis,
    CriterionStatusEnum,
    ExpectedSalary,
    StopFactorAnalysis,
)
from nanimai_platform.domain.scalar.scalars import (
    CandidateID,
    CriterionID,
    ProjectID,
    StopFactorID,
    UserID,
    VacancyID,
)
from nanimai_platform.domain.skill import Skill
from nanimai_platform.domain.vacancy import VacancyStageEnum
from nanimai_platform.utils.update_value import UpdateValue


class CandidateRepositoryError(Exception): ...


class CandidateValidateError(CandidateRepositoryError): ...


class CandidateNotFoundError(CandidateRepositoryError): ...


class CreateCandidateError(CandidateRepositoryError): ...


class ReadCandidateError(CandidateRepositoryError): ...


class UpdateCandidateError(CandidateRepositoryError): ...


class DeleteCandidateError(CandidateRepositoryError): ...


class CandidateRepositoryProtocol(ABC):
    @dataclass
    class CreateCandidateRequest:
        user_id: UserID
        project_id: ProjectID
        vacancy_id: VacancyID
        resume: str
        name: str
        phone_number: str | None
        email: str | None
        website: Url | None
        city: str | None
        country: str | None
        thumbnail_url: str
        experience: int
        expected_salary: ExpectedSalary | None
        notes: str
        dirty: bool
        source: CandidateSourceEnum
        skills: list[Skill]
        status: VacancyStageEnum
        criteria: dict[CriterionID, CriterionAnalysis] | None
        stop_factors: dict[StopFactorID, StopFactorAnalysis] | None
        analysis_status: CandidateAnalysisStatusEnum
        contacts: dict[ContactTypeEnum, str] | None = None

    @abstractmethod
    async def create_candidate(self, request: CreateCandidateRequest) -> Candidate:
        """creates candidate in repository

        Raises:
            CreateCandidateError - not expected exception
            CandidateValidateError - validation error
        Returns:
            Candidate - created candidate
        """
        ...

    @dataclass
    class ReadCandidateRequest:
        id: CandidateID

    @abstractmethod
    async def read_candidate(self, request: ReadCandidateRequest) -> Candidate:
        """reads candidate in repository

        Raises:
            ReadCandidateError - not expected exception
            CandidateValidateError - validation error
            CandidateNotFoundError - candidate not found
        Returns:
            Candidate - read candidate
        """
        ...

    @dataclass
    class UpdateCandidateRequest:
        id: CandidateID

        resume: UpdateValue[str] | None
        name: UpdateValue[str] | None
        phone_number: UpdateValue[str | None] | None
        email: UpdateValue[str | None] | None
        website: UpdateValue[Url | None] | None
        city: UpdateValue[str | None] | None
        country: UpdateValue[str | None] | None
        thumbnail_url: UpdateValue[str] | None
        experience: UpdateValue[int] | None
        expected_salary: UpdateValue[ExpectedSalary | None] | None
        notes: UpdateValue[str] | None
        dirty: UpdateValue[bool] | None
        source: UpdateValue[CandidateSourceEnum] | None
        skills: UpdateValue[list[Skill]] | None
        status: UpdateValue[VacancyStageEnum] | None
        status_history: UpdateValue[set[VacancyStageEnum]] | None
        analysis_status: UpdateValue[CandidateAnalysisStatusEnum] | None
        contacts: UpdateValue[dict[ContactTypeEnum, str]] | None = None

    @abstractmethod
    async def update_candidate(self, request: UpdateCandidateRequest) -> Candidate:
        """updates candidate in repository

        Raises:
            UpdateCandidateError - not expected exception
            CandidateValidateError - validation error
            CandidateNotFoundError - candidate not found
        Returns:
            Candidate - updated candidate
        """
        ...

    @dataclass
    class DeleteCandidateRequest:
        id: CandidateID

    @abstractmethod
    async def delete_candidate(self, request: DeleteCandidateRequest) -> Candidate:
        """deletes candidate in repository

        Raises:
            DeleteCandidateError - not expected exception
            CandidateValidateError - validation error
            CandidateNotFoundError - candidate not found
        Returns:
            Candidate - deleted candidate
        """
        ...

    @dataclass
    class ReadManyCandidatesRequest:
        candidate_ids: list[CandidateID]

    @abstractmethod
    async def read_many_candidates(self, request: ReadManyCandidatesRequest) -> list[Candidate | None]:
        """reads many candidates in repository

        Raises:
            ReadCandidateError - not expected exception
            CandidateValidateError - validation error
            CandidateNotFoundError - candidate not found
        Returns:
            list[Candidate | None] - list of candidates or None if candidate does not exist
        """
        ...

    @dataclass
    class ReadManyCandidatesByProjectRequest:
        project_id: ProjectID

    @abstractmethod
    async def read_many_candidates_by_project(self, request: ReadManyCandidatesByProjectRequest) -> list[Candidate]:
        """reads many candidates by project in repository

        Raises:
            ReadCandidateError - not expected exception
            CandidateValidateError - validation error
        Returns:
            list[Candidate] - list of candidates
        """
        ...

    @dataclass
    class ReadManyCandidatesByVacancyRequest:
        vacancy_id: VacancyID

    @abstractmethod
    async def read_many_candidates_by_vacancy(self, request: ReadManyCandidatesByVacancyRequest) -> list[Candidate]:
        """reads many candidates by vacancy in repository

        Raises:
            ReadCandidateError - not expected exception
            CandidateValidateError - validation error
        Returns:
            list[Candidate] - list of candidates
        """
        ...

    @dataclass
    class ReadManyCandidateCards:
        vacancy_id: VacancyID
        resume: str | None = None
        name: str | None = None
        phone: str | None = None
        email: str | None = None
        city: str | None = None
        country: str | None = None
        notes: str | None = None

    @abstractmethod
    async def read_many_candidate_cards(self, request: ReadManyCandidateCards) -> list[CandidateCard]:
        """reads many candidate card (lite version of candidate object) by vacancy in repository

        Raises:
            ReadCandidateError - not expected exception
            CandidateValidateError - validation error
        Returns:
            list[CandidateCard] - list of candidates
        """
        ...

    @dataclass
    class UpdateCandidateCriterionRequest:
        id: CandidateID

        criterion_id: CriterionID
        score: UpdateValue[float | None] | None
        status: UpdateValue[CriterionStatusEnum | None] | None
        description: UpdateValue[str | None] | None

    @abstractmethod
    async def update_candidate_criterion(self, request: UpdateCandidateCriterionRequest) -> Candidate:
        """updates candidate's criterion in repository

        Raises:
            UpdateCandidateError - not expected exception
            CandidateValidateError - validation error
            CandidateNotFoundError - candidate not found
        Returns:
            Candidate - updated candidate
        """
        ...

    @dataclass
    class SetCandidateCriterion:
        criterion_id: CriterionID
        score: UpdateValue[float | None] | None
        status: UpdateValue[CriterionStatusEnum | None] | None
        description: UpdateValue[str | None] | None

    @dataclass
    class SetCandidateCriteriaRequest:
        id: CandidateID

        updates: list[CandidateRepositoryProtocol.SetCandidateCriterion]

    @abstractmethod
    async def set_candidate_criteria(self, request: SetCandidateCriteriaRequest) -> Candidate:
        """sets candidate's many criteria in repository

        Raises:
            UpdateCandidateError - not expected exception
            CandidateValidateError - validation error
            CandidateNotFoundError - candidate not found
        Returns:
            Candidate - updated candidate
        """
        ...

    @dataclass
    class UpdateCandidateStopFactorRequest:
        id: CandidateID

        stop_factor_id: StopFactorID
        status: UpdateValue[bool | None] | None
        description: UpdateValue[str | None] | None

    @abstractmethod
    async def update_candidate_stop_factor(self, request: UpdateCandidateStopFactorRequest) -> Candidate:
        """updates candidate's stop-factor in repository

        Raises:
            UpdateCandidateError - not expected exception
            CandidateValidateError - validation error
            CandidateNotFoundError - candidate not found
        Returns:
            Candidate - updated candidate
        """
        ...

    @dataclass
    class SetCandidateStopFactor:
        stop_factor_id: StopFactorID
        status: UpdateValue[bool | None] | None
        description: UpdateValue[str | None] | None

    @dataclass
    class SetCandidateStopFactorsRequest:
        id: CandidateID

        updates: list[CandidateRepositoryProtocol.SetCandidateStopFactor]

    @abstractmethod
    async def set_candidate_stop_factors(self, request: SetCandidateStopFactorsRequest) -> Candidate:
        """sets candidate's many stop-factors in repository

        Raises:
            UpdateCandidateError - not expected exception
            CandidateValidateError - validation error
            CandidateNotFoundError - candidate not found
        Returns:
            Candidate - updated candidate
        """
        ...
