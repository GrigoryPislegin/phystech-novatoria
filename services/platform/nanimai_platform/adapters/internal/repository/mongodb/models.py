from datetime import datetime
from typing import TYPE_CHECKING, Any, final

from beanie import Document
from pydantic_core import Url
from pymongo import TEXT, IndexModel

import nanimai_platform.domain as domain

if TYPE_CHECKING:
    type Link[T] = T
else:
    from beanie import Link


class Candidate(Document):
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    # back links
    user: Link["UserProfile"]
    vacancy: Link["Vacancy"]
    project: Link["Project"]
    # document content
    resume: str
    name: str
    city: str | None
    country: str | None
    phone_number: str | None
    email: str | None
    website: Url | None
    thumbnail_url: str
    experience: int
    expected_salary: domain.ExpectedSalary | None
    notes: str
    dirty: bool
    source: domain.CandidateSourceEnum
    skills: list[domain.Skill]
    status: domain.VacancyStageEnum
    status_history: set[domain.VacancyStageEnum] = set()
    analyses: list[Any]
    criteria: dict[domain.CriterionID, domain.CriterionAnalysis]
    stop_factors: dict[domain.StopFactorID, domain.StopFactorAnalysis]
    analysis_status: domain.CandidateAnalysisStatusEnum
    contacts: dict[domain.ContactTypeEnum, str] = {}

    @final
    class Settings:
        name = "candidates"
        indexes = [
            "deleted_at",
            "user.$id",
            "project.$id",
            "vacancy.$id",
            "analysis_status",
            IndexModel(
                [
                    ("resume", TEXT),
                    ("name", TEXT),
                    ("city", TEXT),
                    ("country", TEXT),
                    ("notes", TEXT),
                    ("email", TEXT),
                    ("phone_number", TEXT),
                ],
                name="candidate_text",
                default_language="russian",
            ),
        ]

    def to_domain(self) -> domain.Candidate:
        return domain.Candidate(
            id=domain.CandidateID(self.id),
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
            user_id=domain.UserID(self.user.id),
            project_id=domain.ProjectID(self.project.id),
            vacancy_id=domain.VacancyID(self.vacancy.id),
            resume=self.resume,
            name=self.name,
            city=self.city,
            country=self.country,
            phone_number=self.phone_number,
            email=self.email,
            website=self.website,
            thumbnail_url=self.thumbnail_url,
            experience=self.experience,
            expected_salary=self.expected_salary,
            notes=self.notes,
            dirty=self.dirty,
            source=self.source,
            skills=self.skills,
            status=self.status,
            status_history=self.status_history,
            criteria=self.criteria,
            stop_factors=self.stop_factors,
            analysis_status=self.analysis_status,
            contacts=self.contacts,
        )


class Operation(Document):
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    # back links
    user: Link["UserProfile"]
    # document content
    finished_at: datetime | None
    status: domain.OperationStatus
    usage: list[domain.OperationUsageReport]

    @final
    class Settings:
        name = "operations"
        is_root = True
        indexes = ["deleted_at", "finished_at", "user.$id"]


class ParseVacancyOperation(Operation):
    # back links
    project: Link["Project"]
    filepath: str
    # relations
    created_vacancy: Link["Vacancy"] | None

    def to_domain(self) -> domain.ParseVacancyOperation:
        return domain.ParseVacancyOperation(
            id=domain.OperationID(self.id),
            user_id=domain.UserID(self.user.id),
            filepath=self.filepath,
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
            finished_at=self.finished_at,
            status=self.status,
            usage=self.usage,
            project_id=domain.ProjectID(self.project.id),
            created_vacancy_id=domain.VacancyID(self.created_vacancy.id) if self.created_vacancy else None,
        )


class ParseCandidateOperation(Operation):
    # back links
    vacancy: Link["Vacancy"]
    filepath: str
    # relations
    created_candidate: Link["Candidate"] | None

    def to_domain(self) -> domain.ParseCandidateOperation:
        return domain.ParseCandidateOperation(
            id=domain.OperationID(self.id),
            user_id=domain.UserID(self.user.id),
            filepath=self.filepath,
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
            finished_at=self.finished_at,
            status=self.status,
            usage=self.usage,
            vacancy_id=domain.VacancyID(self.vacancy.id),
            created_candidate_id=domain.CandidateID(self.created_candidate.id) if self.created_candidate else None,
        )


class GenerateAnalysisOperation(Operation):
    # back links
    candidate: Link["Candidate"]
    # relations
    created_analysis: Any | None

    def to_domain(self) -> domain.GenerateAnalysisOperation:
        return domain.GenerateAnalysisOperation(
            id=domain.OperationID(self.id),
            user_id=domain.UserID(self.user.id),
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
            finished_at=self.finished_at,
            status=self.status,
            usage=self.usage,
            candidate_id=domain.CandidateID(self.candidate.id),
            created_analysis_id=domain.AnalysisID(self.created_analysis.id) if self.created_analysis else None,
        )


class Project(Document):
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    # back links
    user: Link["UserProfile"]
    # document content
    title: str
    description: str | None
    # relations
    vacancies: list[Link["Vacancy"]]

    thumbnail_url: str
    statistics: domain.ProjectStatistics
    template_settings: domain.ProjectTemplateSettings

    @final
    class Settings:
        name = "projects"
        indexes = ["deleted_at", "user.$id"]

    def to_domain(self) -> domain.Project:
        return domain.Project(
            id=domain.ProjectID(self.id),
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
            user_id=domain.UserID(self.user.id),
            title=self.title,
            description=self.description,
            thumbnail_url=self.thumbnail_url,
            statistics=self.statistics,
            template_settings=self.template_settings,
        )


class UserProfile(Document):
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    # document content
    email: str
    name: str
    password: str
    thumbnail_url: str
    tariff: domain.Tariff
    tutorials: domain.Tutorials
    # relations
    projects: list[Link["Project"]]

    @final
    class Settings:
        name = "user_profiles"
        indexes = ["email", "deleted_at"]

    def to_domain(self) -> domain.UserProfile:
        return domain.UserProfile(
            id=domain.UserID(self.id),
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
            email=self.email,
            name=self.name,
            password=self.password,
            thumbnail_url=self.thumbnail_url,
            tariff=self.tariff,
            tutorials=self.tutorials,
        )


class Vacancy(Document):
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    # back links
    user: Link["UserProfile"]
    project: Link["Project"]
    # document content
    title: str
    description: str
    specialization: str
    thumbnail_url: str
    status: domain.VacancyStatus
    city: str | None
    country: str | None
    hire_amount: int | None
    salary: domain.SalaryAmountRange | None
    work_type: domain.WorkTypeEnum
    work_format: list[domain.WorkFormatEnum]
    is_internship: bool
    is_temphire: bool
    schedule: list[domain.ScheduleEnum]
    daily_rate: list[int]
    experience: domain.ExperienceEnum
    skills: list[domain.Skill]
    stages: list[domain.VacancyStageStatus]
    publication: domain.VacancyPublication
    statistics: domain.VacancyStatistics
    threshold: float
    # relations
    candidates: list[Link["Candidate"]]

    @final
    class Settings:
        name = "vacancies"
        indexes = ["deleted_at", "user.$id", "project.$id"]

    def to_domain(self) -> domain.Vacancy:
        return domain.Vacancy(
            id=domain.VacancyID(self.id),
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
            user_id=domain.UserID(self.user.id),
            project_id=domain.ProjectID(self.project.id),
            title=self.title,
            description=self.description,
            specialization=self.specialization,
            thumbnail_url=self.thumbnail_url,
            status=self.status,
            city=self.city,
            country=self.country,
            hire_amount=self.hire_amount,
            salary=self.salary,
            work_type=self.work_type,
            work_format=self.work_format,
            is_internship=self.is_internship,
            is_temphire=self.is_temphire,
            schedule=self.schedule,
            daily_rate=self.daily_rate,
            experience=self.experience,
            skills=self.skills,
            stages=self.stages,
            publication=self.publication,
            statistics=self.statistics,
            threshold=self.threshold,
        )


class CustomerContact(Document):
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    name: str
    contact: str
    number_employees: int

    @final
    class Settings:
        name = "customer_contacts"
        indexes = ["deleted_at"]

    def to_domain(self) -> domain.CustomerContact:
        return domain.CustomerContact(
            id=domain.CustomerContactID(self.id),
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
            name=self.name,
            contact=self.contact,
            number_employees=self.number_employees,
        )


class Criterion(Document):
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    # back links
    user: Link["UserProfile"]
    project: Link["Project"]
    vacancy: Link["Vacancy"]
    # document content
    criterion: str
    initial_weight: int
    weight: float
    calculated: bool

    @final
    class Settings:
        name = "criteria"
        indexes = ["deleted_at", "vacancy.$id"]

    def to_domain(self) -> domain.Criterion:
        return domain.Criterion(
            id=domain.CriterionID(self.id),
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
            user_id=domain.UserID(self.user.id),
            project_id=domain.ProjectID(self.project.id),
            vacancy_id=domain.VacancyID(self.vacancy.id),
            criterion=self.criterion,
            initial_weight=self.initial_weight,
            weight=self.weight,
            calculated=self.calculated,
        )


class StopFactor(Document):
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    # back links
    user: Link["UserProfile"]
    project: Link["Project"]
    vacancy: Link["Vacancy"]
    # document content
    stop_factor: str
    initial_weight: int

    @final
    class Settings:
        name = "stop_factors"
        indexes = ["deleted_at", "vacancy.$id"]

    def to_domain(self) -> domain.StopFactor:
        return domain.StopFactor(
            id=domain.StopFactorID(self.id),
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
            user_id=domain.UserID(self.user.id),
            project_id=domain.ProjectID(self.project.id),
            vacancy_id=domain.VacancyID(self.vacancy.id),
            stop_factor=self.stop_factor,
            initial_weight=self.initial_weight,
        )


class OAuth2Profile(Document):
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    # back links
    user: Link["UserProfile"]
    # document content
    source: domain.Oauth2SourceEnum
    token: domain.Token | None

    @final
    class Settings:
        name = "oauth2_profiles"
        indexes = ["deleted_at", "user.$id", "source"]

    def to_domain(self) -> domain.OAuth2Profile:
        return domain.OAuth2Profile(
            id=domain.OAuth2ProfileID(self.id),
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
            user_id=domain.UserID(self.user.id),
            source=self.source,
            token=self.token,
        )


class Statistics(Document):
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    # back links
    user: Link["UserProfile"]
    project: Link["Project"]
    vacancy: Link["Vacancy"]
    # document content
    project_statistics: domain.ProjectStatistics
    vacancy_statistics: domain.VacancyCandidatesStatistics
    score_statistics: domain.CandidateScoreStatistics
    stage_statistics: domain.CandidateStageStatistics
    criterion_stop_factor_status_statistics: domain.CandidateCriterionStopFactorStatusStatistics
    date_increase_statistics: domain.CandidateDateIncreaseStatistics
    salary_statistics: domain.CandidateSalaryStatistics

    @final
    class Settings:
        name = "statistics"
        indexes = ["deleted_at", "vacancy.$id", "project.$id"]

    def to_domain(self) -> domain.Statistics:
        return domain.Statistics(
            id=domain.StatisticsID(self.id),
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
            user_id=domain.UserID(self.user.id),
            project_id=domain.ProjectID(self.project.id),
            vacancy_id=domain.VacancyID(self.vacancy.id),
            project_statistics=self.project_statistics,
            vacancy_statistics=self.vacancy_statistics,
            score_statistics=self.score_statistics,
            stage_statistics=self.stage_statistics,
            criterion_stop_factor_status_statistics=self.criterion_stop_factor_status_statistics,
            date_increase_statistics=self.date_increase_statistics,
            salary_statistics=self.salary_statistics,
        )


ALL_MODELS = [
    Vacancy,
    Candidate,
    Operation,
    ParseVacancyOperation,
    ParseCandidateOperation,
    GenerateAnalysisOperation,
    Project,
    UserProfile,
    CustomerContact,
    Criterion,
    StopFactor,
    OAuth2Profile,
    Statistics,
]
