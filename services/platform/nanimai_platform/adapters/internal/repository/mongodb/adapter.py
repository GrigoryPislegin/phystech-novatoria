import asyncio
from datetime import UTC, datetime
from typing import Any, Self, final, override

import beanie
import pydantic
import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorClientSession
from pydantic_extra_types.currency_code import ISO4217 as CurrencyISO4217

import nanimai_platform.domain as domain
import nanimai_platform.protocols.internal.repository as protocol
from nanimai_platform.protocols.internal.repository.candidate import CandidateRepositoryProtocol
from nanimai_platform.protocols.internal.repository.criterion import CriterionRepositoryProtocol
from nanimai_platform.protocols.internal.repository.customer_contact import CustomerContactRepositoryProtocol
from nanimai_platform.protocols.internal.repository.oauth2 import OAuth2RepositoryProtocol
from nanimai_platform.protocols.internal.repository.operation import OperationRepositoryProtocol
from nanimai_platform.protocols.internal.repository.project import ProjectRepositoryProtocol
from nanimai_platform.protocols.internal.repository.statistics import StatisticsRepositoryProtocol
from nanimai_platform.protocols.internal.repository.stop_factor import StopFactorRepositoryProtocol
from nanimai_platform.protocols.internal.repository.user_profile import UserRepositoryProtocol
from nanimai_platform.protocols.internal.repository.vacancy import VacancyRepositoryProtocol
from nanimai_platform.utils.logging_span import span
from nanimai_platform.utils.update_value import UpdateValue

from .models import (
    ALL_MODELS,
    Candidate,
    Criterion,
    CustomerContact,
    GenerateAnalysisOperation,
    OAuth2Profile,
    Operation,
    ParseCandidateOperation,
    ParseVacancyOperation,
    Project,
    Statistics,
    StopFactor,
    UserProfile,
    Vacancy,
)

log = structlog.stdlib.get_logger("app.adapters.MongoRepositoryAdapter")

type ClientT = dict[str, beanie.Document]


@final
class MongoRepositoryAdapter(
    ProjectRepositoryProtocol,
    CandidateRepositoryProtocol,
    VacancyRepositoryProtocol,
    OperationRepositoryProtocol,
    UserRepositoryProtocol,
    CustomerContactRepositoryProtocol,
    CriterionRepositoryProtocol,
    OAuth2RepositoryProtocol,
    StopFactorRepositoryProtocol,
    StatisticsRepositoryProtocol,
):
    _client: AsyncIOMotorClient[ClientT]
    T = AsyncIOMotorClientSession  # type: ignore

    def __init__(self, client: AsyncIOMotorClient[ClientT], database_name: str):
        self._client = client
        self._database_name = database_name

    def _build_filter_conditions(self, request: CandidateRepositoryProtocol.ReadManyCandidateCards) -> dict[str, Any]:
        match_conditions: dict[str, Any] = {}

        if request.resume:
            match_conditions["$text"] = {"$search": request.resume}
        if request.name:
            match_conditions["name"] = {"$regex": request.name, "$options": "i"}
        if request.phone:
            match_conditions["phone_number"] = request.phone
        if request.email:
            match_conditions["email"] = request.email
        if request.city:
            match_conditions["city"] = {"$regex": f"^{request.city}$", "$options": "i"}
        if request.country:
            match_conditions["country"] = {"$regex": f"^{request.country}$", "$options": "i"}
        if request.notes:
            match_conditions["notes"] = {"$regex": request.notes, "$options": "i"}

        return match_conditions

    @classmethod
    async def create(cls, client: AsyncIOMotorClient[ClientT]) -> Self:
        try:
            database_name = "nanimai_platform"
            await beanie.init_beanie(client.get_database(database_name), document_models=ALL_MODELS)
        except Exception as e:
            raise protocol.RepositoryConnectionError(f"Connection error to mongodb with error: {e}") from e
        return cls(client, database_name)

    @span(op="mongodb_repository", name="create_project")
    @override
    async def create_project(self, request: ProjectRepositoryProtocol.CreateProjectRequest) -> domain.Project:
        try:
            user = await UserProfile.find_one({"_id": request.user_id})
            if user is None:
                log.error("user with id does not exist", user_id=request.user_id)
                raise protocol.UserNotFoundError("user with id does not exist")

            template_settings = domain.ProjectTemplateSettings(
                logo_url=None,
                logo_format=None,
                main_color=None,
                without_nanimai_attributes=False,
            )

            dbmodel = Project(
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                deleted_at=None,
                user=user,
                title=request.title,
                description=request.description,
                vacancies=[],
                thumbnail_url=request.thumbnail_url,
                statistics=request.statistics,
                template_settings=template_settings,
            )
            dbmodel = await dbmodel.insert()

            if dbmodel.id is None:
                raise protocol.ProjectRepositoryError("project creation failed")

            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.ProjectValidateError("validation error") from e
        except protocol.UserNotFoundError as e:
            log.error("failed with user not found error", err=e)
            raise e
        except protocol.ProjectRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.CreateProjectError("unknown error") from e

    @span(op="mongodb_repository", name="read_project")
    @override
    async def read_project(self, request: ProjectRepositoryProtocol.ReadProjectRequest) -> domain.Project:
        try:
            dbmodel = await Project.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("project with id does not exist", project_id=request.id)
                raise protocol.ProjectNotFoundError("project does not exist")

            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.ProjectValidateError("validation error") from e
        except protocol.ProjectNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadProjectError("unknown error") from e

    @span(op="mongodb_repository", name="update_project")
    @override
    async def update_project(self, request: ProjectRepositoryProtocol.UpdateProjectRequest) -> domain.Project:
        try:
            dbmodel = await Project.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("project with id does not exist", project_id=request.id)
                raise protocol.ProjectNotFoundError("project does not exist")

            if isinstance(request.title, UpdateValue):
                dbmodel.title = request.title.value

            if isinstance(request.description, UpdateValue):
                dbmodel.description = request.description.value

            if isinstance(request.vacancies, UpdateValue):
                dbmodel.vacancies = await Vacancy.find({
                    "_id": {"$in": request.vacancies.value},
                    "deleted_at": None,
                }).to_list()

            if isinstance(request.statistics, UpdateValue):
                dbmodel.statistics = request.statistics.value

            if isinstance(request.updated_at, UpdateValue):
                dbmodel.updated_at = request.updated_at.value

            dbmodel = await dbmodel.save()

            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.ProjectValidateError("validation error") from e
        except protocol.ProjectNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.UpdateProjectError("unknown error") from e

    @span(op="mongodb_repository", name="delete_project")
    @override
    async def delete_project(self, request: ProjectRepositoryProtocol.DeleteProjectRequest) -> domain.Project:
        try:
            dbmodel = await Project.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("project with id does not exist", project_id=request.id)
                raise protocol.ProjectNotFoundError("project does not exist")

            dbmodel.deleted_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()

            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.ProjectValidateError("validation error") from e
        except protocol.ProjectNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.DeleteProjectError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_projects")
    @override
    async def read_many_projects(
        self, request: ProjectRepositoryProtocol.ReadManyProjectsRequest
    ) -> list[domain.Project | None]:
        try:
            dbmodels = await Project.find({"_id": {"$in": request.project_ids}, "deleted_at": None}).to_list()

            await asyncio.gather(*[dbmodel.fetch_all_links() for dbmodel in dbmodels])

            mapping = {str(dbmodel.id): dbmodel.to_domain() for dbmodel in dbmodels}
            return [mapping.get(str(dbmodel.id)) for dbmodel in dbmodels]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.ProjectValidateError("validation error") from e
        except protocol.ProjectRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadProjectError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_projects_by_user")
    @override
    async def read_many_projects_by_user(
        self, request: ProjectRepositoryProtocol.ReadManyProjectsByUserRequest
    ) -> list[domain.Project]:
        try:
            dbmodels = await Project.find({"user.$id": request.user_id, "deleted_at": None}).to_list()
            await asyncio.gather(*[dbmodel.fetch_all_links() for dbmodel in dbmodels])

            return [dbmodel.to_domain() for dbmodel in dbmodels]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.ProjectValidateError("validation error") from e
        except protocol.ProjectRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadProjectError("unknown error") from e

    @span(op="mongodb_repository", name="update_project_settings")
    @override
    async def update_project_settings(
        self, request: ProjectRepositoryProtocol.UpdateProjectSettingsRequest
    ) -> domain.Project:
        try:
            dbmodel = await Project.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("project with id does not exist", project_id=request.id)
                raise protocol.ProjectNotFoundError("project does not exist")

            dbmodel.template_settings.logo_url = request.logo_url
            dbmodel.template_settings.logo_format = request.logo_format
            dbmodel.template_settings.main_color = request.main_color
            dbmodel.template_settings.without_nanimai_attributes = request.without_nanimai_attributes

            dbmodel.updated_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()

            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.ProjectValidateError("validation error") from e
        except protocol.ProjectNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.UpdateProjectError("unknown error") from e

    @span(op="mongodb_repository", name="create_vacancy")
    @override
    async def create_vacancy(self, request: VacancyRepositoryProtocol.CreateVacancyRequest) -> domain.Vacancy:
        try:
            project = await Project.find_one({"_id": request.project_id, "deleted_at": None})
            if project is None:
                log.error("project with id does not exist", project_id=request.project_id)
                raise protocol.ProjectNotFoundError("project does not exist")

            dbmodel = Vacancy(
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                deleted_at=None,
                user=project.user,
                project=project,
                title=request.title,
                description=request.description,
                specialization=request.specialization,
                thumbnail_url=request.thumbnail_url,
                status=request.status,
                city=request.city,
                country=request.country,
                hire_amount=request.hire_amount,
                salary=request.salary,
                work_type=request.work_type,
                work_format=request.work_format,
                is_internship=request.is_internship,
                is_temphire=request.is_temphire,
                schedule=request.schedule,
                daily_rate=request.daily_rate,
                experience=request.experience,
                skills=request.skills,
                stages=request.stages,
                publication=request.publication,
                candidates=[],
                statistics=request.statistics,
                threshold=request.threshold,
            )
            dbmodel = await dbmodel.insert()

            if dbmodel.id is None:
                raise protocol.VacancyRepositoryError("vacancy creation failed")

            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.VacancyValidateError("validation error") from e
        except protocol.ProjectNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except protocol.VacancyRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.CreateVacancyError("unknown error") from e

    @span(op="mongodb_repository", name="read_vacancy")
    @override
    async def read_vacancy(self, request: VacancyRepositoryProtocol.ReadVacancyRequest) -> domain.Vacancy:
        try:
            dbmodel = await Vacancy.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("vacancy with id does not exist", vacancy_id=request.id)
                raise protocol.VacancyNotFoundError("vacancy does not exist")
            log.debug("vacancy found", vacancy=dbmodel)
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.VacancyValidateError("validation error") from e
        except protocol.VacancyNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadVacancyError("unknown error") from e

    @span(op="mongodb_repository", name="update_vacancy")
    @override
    async def update_vacancy(self, request: VacancyRepositoryProtocol.UpdateVacancyRequest) -> domain.Vacancy:  # noqa: C901
        try:
            dbmodel = await Vacancy.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("vacancy with id does not exist", vacancy_id=request.id)
                raise protocol.VacancyNotFoundError("vacancy does not exist")
            if isinstance(request.title, UpdateValue):
                dbmodel.title = request.title.value
            if isinstance(request.description, UpdateValue):
                dbmodel.description = request.description.value
            if isinstance(request.specialization, UpdateValue):
                dbmodel.specialization = request.specialization.value
            if isinstance(request.status, UpdateValue):
                dbmodel.status = request.status.value
            if isinstance(request.city, UpdateValue):
                dbmodel.city = request.city.value
            if isinstance(request.country, UpdateValue):
                dbmodel.country = request.country.value
            if isinstance(request.hire_amount, UpdateValue):
                dbmodel.hire_amount = request.hire_amount.value
            if isinstance(request.salary, UpdateValue):
                dbmodel.salary = request.salary.value
            if isinstance(request.work_type, UpdateValue):
                dbmodel.work_type = request.work_type.value
            if isinstance(request.is_internship, UpdateValue):
                dbmodel.is_internship = request.is_internship.value
            if isinstance(request.is_temphire, UpdateValue):
                dbmodel.is_temphire = request.is_temphire.value
            if isinstance(request.schedule, UpdateValue):
                dbmodel.schedule = request.schedule.value
            if isinstance(request.daily_rate, UpdateValue):
                dbmodel.daily_rate = request.daily_rate.value
            if isinstance(request.experience, UpdateValue):
                dbmodel.experience = request.experience.value
            if isinstance(request.skills, UpdateValue):
                dbmodel.skills = request.skills.value
            if isinstance(request.stages, UpdateValue):
                dbmodel.stages = request.stages.value
            if isinstance(request.publication, UpdateValue):
                dbmodel.publication = request.publication.value
            if isinstance(request.candidates, UpdateValue):
                dbmodel.candidates = await Candidate.find(
                    {
                        "_id": {"$in": request.candidates.value},
                        "deleted_at": None,
                    },
                ).to_list()
            if isinstance(request.statistics, UpdateValue):
                dbmodel.statistics = request.statistics.value
            if isinstance(request.threshold, UpdateValue):
                dbmodel.threshold = request.threshold.value
            if isinstance(request.updated_at, UpdateValue):
                dbmodel.updated_at = request.updated_at.value

            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.VacancyValidateError("validation error") from e
        except protocol.VacancyNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.UpdateVacancyError("unknown error") from e

    @span(op="mongodb_repository", name="delete_vacancy")
    @override
    async def delete_vacancy(self, request: VacancyRepositoryProtocol.DeleteVacancyRequest) -> domain.Vacancy:
        try:
            dbmodel = await Vacancy.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("vacancy with id does not exist", vacancy_id=request.id)
                raise protocol.VacancyNotFoundError("vacancy does not exist")
            dbmodel.deleted_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.VacancyValidateError("validation error") from e
        except protocol.VacancyNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.DeleteVacancyError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_vacancies")
    @override
    async def read_many_vacancies(
        self, request: VacancyRepositoryProtocol.ReadManyVacanciesRequest
    ) -> list[domain.Vacancy | None]:
        try:
            dbmodels = await Vacancy.find(
                {"_id": {"$in": request.vacancy_ids}, "deleted_at": None},
            ).to_list()
            await asyncio.gather(*[dbmodel.fetch_all_links() for dbmodel in dbmodels])
            mapping = {str(dbmodel.id): dbmodel.to_domain() for dbmodel in dbmodels}
            return [mapping.get(str(dbmodel.id)) for dbmodel in dbmodels]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.VacancyValidateError("validation error") from e
        except protocol.VacancyRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadVacancyError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_vacancies_by_project")
    @override
    async def read_many_vacancies_by_project(
        self, request: VacancyRepositoryProtocol.ReadManyVacanciesByProjectRequest
    ) -> list[domain.Vacancy]:
        try:
            dbmodels = await Vacancy.find(
                {"project.$id": request.project_id, "deleted_at": None},
            ).to_list()
            await asyncio.gather(*[dbmodel.fetch_all_links() for dbmodel in dbmodels])

            return [dbmodel.to_domain() for dbmodel in dbmodels]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.VacancyValidateError("validation error") from e
        except protocol.VacancyRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadVacancyError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_published_vacancies")
    @override
    async def read_many_published_vacancies(
        self, request: protocol.VacancyRepositoryProtocol.ReadManyPublishedVacanciesRequest
    ) -> list[domain.Vacancy]:
        try:
            if request.source == domain.VacancyPublicationSourceEnum.HH:
                publication_to_find = {"publication.hh.state": domain.PublicationStatusEnum.PUBLISHED.value}
            elif request.source == domain.VacancyPublicationSourceEnum.AVITO:
                publication_to_find = {"publication.avito.state": domain.PublicationStatusEnum.PUBLISHED.value}
            else:
                raise protocol.VacancyRepositoryError

            dbmodels = await Vacancy.find({
                "$and": [
                    {"deleted_at": None},
                    publication_to_find,
                ]
            }).to_list()
            await asyncio.gather(*[dbmodel.fetch_all_links() for dbmodel in dbmodels])
            return [dbmodel.to_domain() for dbmodel in dbmodels]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.VacancyValidateError("validation error") from e
        except protocol.VacancyRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadVacancyError("unknown error") from e

    @span(op="mongodb_repository", name="create_candidate")
    @override
    async def create_candidate(self, request: CandidateRepositoryProtocol.CreateCandidateRequest) -> domain.Candidate:
        try:
            vacancy = await Vacancy.find_one({"_id": request.vacancy_id, "deleted_at": None})
            if vacancy is None:
                log.error("vacancy with id does not exist", vacancy_id=request.vacancy_id)
                raise protocol.VacancyNotFoundError("vacancy does not exist")

            dbmodel = Candidate(
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                deleted_at=None,
                user=vacancy.user,
                project=vacancy.project,
                vacancy=vacancy,
                resume=request.resume,
                name=request.name,
                city=request.city,
                country=request.country,
                phone_number=request.phone_number,
                email=request.email,
                website=request.website,
                thumbnail_url=request.thumbnail_url,
                experience=request.experience,
                expected_salary=request.expected_salary,
                notes=request.notes,
                dirty=request.dirty,
                source=request.source,
                skills=request.skills,
                status=request.status,
                status_history={request.status},
                analyses=[],
                criteria=request.criteria or {},
                stop_factors=request.stop_factors or {},
                analysis_status=request.analysis_status,
                contacts=request.contacts or {},
            )
            dbmodel = await dbmodel.insert()

            if dbmodel.id is None:
                raise protocol.CandidateRepositoryError("candidate creation failed")

            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CandidateValidateError("validation error") from e
        except protocol.VacancyNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.CreateCandidateError("unknown error") from e

    @span(op="mongodb_repository", name="read_candidate")
    @override
    async def read_candidate(self, request: CandidateRepositoryProtocol.ReadCandidateRequest) -> domain.Candidate:
        try:
            dbmodel = await Candidate.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("candidate with id does not exist", candidate_id=request.id)
                raise protocol.CandidateNotFoundError("candidate does not exist")
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CandidateValidateError("validation error") from e
        except protocol.CandidateNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadCandidateError("unknown error") from e

    @span(op="mongodb_repository", name="update_candidate")
    @override
    async def update_candidate(  # noqa: C901
        self, request: CandidateRepositoryProtocol.UpdateCandidateRequest
    ) -> domain.Candidate:
        try:
            dbmodel = await Candidate.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("candidate with id does not exist", candidate_id=request.id)
                raise protocol.CandidateNotFoundError("candidate does not exist")
            if isinstance(request.name, UpdateValue):
                dbmodel.name = request.name.value
            if isinstance(request.phone_number, UpdateValue):
                dbmodel.phone_number = request.phone_number.value
            if isinstance(request.email, UpdateValue):
                dbmodel.email = request.email.value
            if isinstance(request.website, UpdateValue):
                dbmodel.website = request.website.value
            if isinstance(request.resume, UpdateValue):
                dbmodel.resume = request.resume.value
            if isinstance(request.city, UpdateValue):
                dbmodel.city = request.city.value
            if isinstance(request.country, UpdateValue):
                dbmodel.country = request.country.value
            if isinstance(request.skills, UpdateValue):
                dbmodel.skills = request.skills.value
            if isinstance(request.status, UpdateValue):
                dbmodel.status = request.status.value
            if isinstance(request.status_history, UpdateValue):
                dbmodel.status_history = request.status_history.value
            if isinstance(request.thumbnail_url, UpdateValue):
                dbmodel.thumbnail_url = request.thumbnail_url.value
            if isinstance(request.experience, UpdateValue):
                dbmodel.experience = request.experience.value
            if isinstance(request.expected_salary, UpdateValue):
                dbmodel.expected_salary = request.expected_salary.value
            if isinstance(request.notes, UpdateValue):
                dbmodel.notes = request.notes.value
            if isinstance(request.dirty, UpdateValue):
                dbmodel.dirty = request.dirty.value
            if isinstance(request.source, UpdateValue):
                dbmodel.source = request.source.value
            if isinstance(request.analysis_status, UpdateValue):
                dbmodel.analysis_status = request.analysis_status.value
            if isinstance(request.contacts, UpdateValue):
                dbmodel.contacts = request.contacts.value

            dbmodel.updated_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CandidateValidateError("validation error") from e
        except protocol.CandidateNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.UpdateCandidateError("unknown error") from e

    @span(op="mongodb_repository", name="delete_candidate")
    @override
    async def delete_candidate(self, request: CandidateRepositoryProtocol.DeleteCandidateRequest) -> domain.Candidate:
        try:
            dbmodel = await Candidate.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("candidate with id does not exist", candidate_id=request.id)
                raise protocol.CandidateNotFoundError("candidate does not exist")
            dbmodel.deleted_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CandidateValidateError("validation error") from e
        except protocol.CandidateNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.DeleteCandidateError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_candidates")
    @override
    async def read_many_candidates(
        self, request: CandidateRepositoryProtocol.ReadManyCandidatesRequest
    ) -> list[domain.Candidate | None]:
        try:
            dbmodels = await Candidate.find({"_id": {"$in": request.candidate_ids}, "deleted_at": None}).to_list()
            await asyncio.gather(*[dbmodel.fetch_all_links() for dbmodel in dbmodels])
            mapping = {str(dbmodel.id): dbmodel.to_domain() for dbmodel in dbmodels}
            return [mapping.get(str(dbmodel.id)) for dbmodel in dbmodels]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CandidateValidateError("validation error") from e
        except protocol.CandidateRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadCandidateError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_candidates_by_project")
    @override
    async def read_many_candidates_by_project(
        self, request: CandidateRepositoryProtocol.ReadManyCandidatesByProjectRequest
    ) -> list[domain.Candidate]:
        try:
            dbmodels = await Candidate.find({"project.$id": request.project_id, "deleted_at": None}).to_list()
            await asyncio.gather(*[dbmodel.fetch_all_links() for dbmodel in dbmodels])

            return [dbmodel.to_domain() for dbmodel in dbmodels]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CandidateValidateError("validation error") from e
        except protocol.CandidateRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadCandidateError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_candidates_by_vacancy")
    @override
    async def read_many_candidates_by_vacancy(
        self, request: CandidateRepositoryProtocol.ReadManyCandidatesByVacancyRequest
    ) -> list[domain.Candidate]:
        try:
            dbmodels = await Candidate.find({"vacancy.$id": request.vacancy_id, "deleted_at": None}).to_list()
            await asyncio.gather(*[dbmodel.fetch_all_links() for dbmodel in dbmodels])

            return [dbmodel.to_domain() for dbmodel in dbmodels]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CandidateValidateError("validation error") from e
        except protocol.CandidateRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadCandidateError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_candidate_cards")
    @override
    async def read_many_candidate_cards(
        self, request: CandidateRepositoryProtocol.ReadManyCandidateCards
    ) -> list[domain.CandidateCard]:
        try:
            match_conditions = {"vacancy.$id": request.vacancy_id, "deleted_at": None}
            has_filters = any([
                request.resume,
                request.name,
                request.phone,
                request.email,
                request.city,
                request.country,
                request.notes,
            ])
            if has_filters:
                filter_conditions = self._build_filter_conditions(request)
                match_conditions.update(filter_conditions)

            pl = [
                {"$match": match_conditions},
                {
                    "$project": {
                        "id": "$_id",
                        "created_at": 1,
                        "updated_at": 1,
                        "deleted_at": 1,
                        "user_id": "$user.$id",
                        "project_id": "$project.$id",
                        "vacancy_id": "$vacancy.$id",
                        "name": 1,
                        "experience": 1,
                        "expected_salary": 1,
                        "notes_preview": "$notes",
                        "dirty": 1,
                        "thumbnail_url": 1,
                        "source": 1,
                        "status": 1,
                        "status_history": 1,
                        "criteria": 1,
                        "stop_factors": 1,
                        "analysis_status": 1,
                        "contacts": 1,
                    }
                },
            ]

            dbmodels = await Candidate.aggregate(pl).to_list()

            return [domain.CandidateCard.model_validate(dbmodel) for dbmodel in dbmodels]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CandidateValidateError("validation error") from e
        except protocol.CandidateRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadCandidateError("unknown error") from e

    @span(op="mongodb_repository", name="update_candidate_criterion")
    @override
    async def update_candidate_criterion(  # noqa: C901
        self, request: CandidateRepositoryProtocol.UpdateCandidateCriterionRequest
    ) -> domain.Candidate:
        try:
            dbmodel = await Candidate.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("candidate with id does not exist", candidate_id=request.id)
                raise protocol.CandidateNotFoundError("candidate does not exist")

            criterion_path = f"criteria.{request.criterion_id}"
            to_set: dict[str, Any] = {}
            to_set["updated_at"] = datetime.now(UTC)
            if request.criterion_id in dbmodel.criteria:
                if isinstance(request.score, UpdateValue):
                    to_set[f"{criterion_path}.score"] = request.score.value
                if isinstance(request.status, UpdateValue):
                    to_set[f"{criterion_path}.status"] = request.status.value
                if isinstance(request.description, UpdateValue):
                    to_set[f"{criterion_path}.description"] = request.description.value

                if len(to_set) > 1:
                    dbmodel = await dbmodel.update({"$set": to_set})

            else:
                to_set[f"{criterion_path}.score"] = (
                    request.score.value if isinstance(request.score, UpdateValue) else None
                )
                to_set[f"{criterion_path}.status"] = (
                    request.status.value if isinstance(request.status, UpdateValue) else None
                )
                to_set[f"{criterion_path}.description"] = (
                    request.description.value if isinstance(request.description, UpdateValue) else None
                )

                if len(to_set) > 1:
                    dbmodel = await dbmodel.update({"$set": to_set})

            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CandidateValidateError("validation error") from e
        except protocol.CandidateNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.UpdateCandidateError("unknown error") from e

    @span(op="mongodb_repository", name="set_candidate_criteria")
    @override
    async def set_candidate_criteria(  # noqa: C901
        self, request: CandidateRepositoryProtocol.SetCandidateCriteriaRequest
    ) -> domain.Candidate:
        try:
            dbmodel = await Candidate.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("candidate with id does not exist", candidate_id=request.id)
                raise protocol.CandidateNotFoundError("candidate does not exist")

            to_set: dict[str, Any] = {}
            for update in request.updates:
                criterion_path = f"criteria.{update.criterion_id}"
                if update.criterion_id in dbmodel.criteria:
                    if isinstance(update.score, UpdateValue):
                        to_set[f"{criterion_path}.score"] = update.score.value
                    if isinstance(update.status, UpdateValue):
                        to_set[f"{criterion_path}.status"] = update.status.value
                    if isinstance(update.description, UpdateValue):
                        to_set[f"{criterion_path}.description"] = update.description.value

                else:
                    to_set[f"{criterion_path}.score"] = (
                        update.score.value if isinstance(update.score, UpdateValue) else None
                    )
                    to_set[f"{criterion_path}.status"] = (
                        update.status.value if isinstance(update.status, UpdateValue) else None
                    )
                    to_set[f"{criterion_path}.description"] = (
                        update.description.value if isinstance(update.description, UpdateValue) else None
                    )

            if len(to_set) > 0:
                to_set["updated_at"] = datetime.now(UTC)
                dbmodel = await dbmodel.update({"$set": to_set})

            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CandidateValidateError("validation error") from e
        except protocol.CandidateNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.UpdateCandidateError("unknown error") from e

    @span(op="mongodb_repository", name="update_candidate_stop_factor")
    @override
    async def update_candidate_stop_factor(  # noqa: C901
        self, request: CandidateRepositoryProtocol.UpdateCandidateStopFactorRequest
    ) -> domain.Candidate:
        try:
            dbmodel = await Candidate.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("candidate with id does not exist", candidate_id=request.id)
                raise protocol.CandidateNotFoundError("candidate does not exist")

            stop_factor_path = f"stop_factors.{request.stop_factor_id}"
            to_set: dict[str, Any] = {}
            to_set["updated_at"] = datetime.now(UTC)

            if request.stop_factor_id in dbmodel.stop_factors:
                if isinstance(request.status, UpdateValue):
                    to_set[f"{stop_factor_path}.status"] = request.status.value
                if isinstance(request.description, UpdateValue):
                    to_set[f"{stop_factor_path}.description"] = request.description.value

                if len(to_set) > 1:
                    dbmodel = await dbmodel.update({"$set": to_set})

            else:
                to_set[f"{stop_factor_path}.status"] = (
                    request.status.value if isinstance(request.status, UpdateValue) else None
                )
                to_set[f"{stop_factor_path}.description"] = (
                    request.description.value if isinstance(request.description, UpdateValue) else None
                )

                if len(to_set) > 1:
                    dbmodel = await dbmodel.update({"$set": to_set})

            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CandidateValidateError("validation error") from e
        except protocol.CandidateNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.UpdateCandidateError("unknown error") from e

    @span(op="mongodb_repository", name="set_candidate_stop_factors")
    @override
    async def set_candidate_stop_factors(  # noqa: C901
        self, request: CandidateRepositoryProtocol.SetCandidateStopFactorsRequest
    ) -> domain.Candidate:
        try:
            dbmodel = await Candidate.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("candidate with id does not exist", candidate_id=request.id)
                raise protocol.CandidateNotFoundError("candidate does not exist")

            to_set: dict[str, Any] = {}

            for update in request.updates:
                stop_factor_path = f"stop_factors.{update.stop_factor_id}"
                if update.stop_factor_id in dbmodel.stop_factors:
                    if isinstance(update.status, UpdateValue):
                        to_set[f"{stop_factor_path}.status"] = update.status.value
                    if isinstance(update.description, UpdateValue):
                        to_set[f"{stop_factor_path}.description"] = update.description.value

                else:
                    to_set[f"{stop_factor_path}.status"] = (
                        update.status.value if isinstance(update.status, UpdateValue) else None
                    )
                    to_set[f"{stop_factor_path}.description"] = (
                        update.description.value if isinstance(update.description, UpdateValue) else None
                    )

            if len(to_set) > 0:
                to_set["updated_at"] = datetime.now(UTC)
                dbmodel = await dbmodel.update({"$set": to_set})

            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CandidateValidateError("validation error") from e
        except protocol.CandidateNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.UpdateCandidateError("unknown error") from e

    @span(op="mongodb_repository", name="create_parse_vacancy_operation")
    @override
    async def create_parse_vacancy_operation(
        self,
        request: OperationRepositoryProtocol.CreateParseVacancyOperationRequest,
    ) -> domain.ParseVacancyOperation:
        try:
            project = await Project.find_one({"_id": request.project_id, "deleted_at": None})
            if project is None:
                log.error("project with id does not exist", project_id=request.project_id)
                raise protocol.ProjectNotFoundError("project does not exist")

            dbmodel = ParseVacancyOperation(
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                deleted_at=None,
                user=project.user,
                finished_at=None,
                status=domain.OperationStatus.PENDING,
                usage=[],
                project=project,
                filepath=request.filepath,
                created_vacancy=None,
            )
            dbmodel = await dbmodel.insert()
            await dbmodel.fetch_all_links()

            if dbmodel.id is None:
                raise protocol.OperationRepositoryError("operation creation failed")

            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.OperationValidateError("validation error") from e
        except protocol.ProjectNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except protocol.OperationRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.CreateOperationError("unknown error") from e

    @span(op="mongodb_repository", name="create_parse_candidate_operation")
    @override
    async def create_parse_candidate_operation(
        self,
        request: OperationRepositoryProtocol.CreateParseCandidateOperationRequest,
    ) -> domain.ParseCandidateOperation:
        try:
            vacancy = await Vacancy.find_one({"_id": request.vacancy_id, "deleted_at": None})
            if vacancy is None:
                log.error("vacancy with id does not exist", vacancy_id=request.vacancy_id)
                raise protocol.VacancyNotFoundError("vacancy does not exist")

            dbmodel = ParseCandidateOperation(
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                deleted_at=None,
                user=vacancy.user,
                finished_at=None,
                status=domain.OperationStatus.PENDING,
                usage=[],
                vacancy=vacancy,
                filepath=request.filepath,
                created_candidate=None,
            )
            dbmodel = await dbmodel.insert()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.OperationValidateError("validation error") from e
        except protocol.VacancyNotFoundError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.CreateOperationError("unknown error") from e

    @span(op="mongodb_repository", name="create_generate_analysis_operation")
    @override
    async def create_generate_analysis_operation(
        self,
        request: OperationRepositoryProtocol.CreateGenerateAnalysisOperationRequest,
    ) -> domain.GenerateAnalysisOperation:
        try:
            candidate = await Candidate.find_one({"_id": request.candidate_id, "deleted_at": None})
            if candidate is None:
                log.error("candidate with id does not exist", candidate_id=request.candidate_id)
                raise protocol.CandidateNotFoundError("candidate does not exist")
            dbmodel = GenerateAnalysisOperation(
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                deleted_at=None,
                user=candidate.user,
                finished_at=None,
                status=domain.OperationStatus.PENDING,
                usage=[],
                candidate=candidate,
                created_analysis=None,
            )
            dbmodel = await dbmodel.insert()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.OperationValidateError("validation error") from e
        except protocol.CandidateNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.CreateOperationError("unknown error") from e

    @span(op="mongodb_repository", name="read_operation")
    @override
    async def read_operation(self, request: OperationRepositoryProtocol.ReadOperationRequest) -> domain.Operation:
        try:
            db_model = await Operation.find_one(
                {"_id": request.id, "deleted_at": None},
                with_children=True,
            )
            if db_model is None:
                log.error("operation with id does not exist", operation_id=request.id)
                raise protocol.OperationNotFoundError("operation does not exist")
            await db_model.fetch_all_links()

            if not isinstance(db_model, ParseVacancyOperation | ParseCandidateOperation | GenerateAnalysisOperation):
                raise protocol.UnknownOperationTypeError(f"unknown operation type: {type(db_model)}")

            return db_model.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.OperationValidateError("validation error") from e
        except protocol.OperationNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except protocol.UnknownOperationTypeError as e:
            log.error("failed with unknown type error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadOperationError("unknown error") from e

    @span(op="mongodb_repository", name="update_parse_vacancy_operation")
    @override
    async def update_parse_vacancy_operation(
        self,
        request: OperationRepositoryProtocol.UpdateParseVacancyOperationRequest,
    ) -> domain.ParseVacancyOperation:
        try:
            dbmodel = await ParseVacancyOperation.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("operation with id does not exist", operation_id=request.id)
                raise protocol.OperationNotFoundError("operation does not exist")
            if request.finished_at is not None:
                dbmodel.finished_at = request.finished_at
            if request.status is not None:
                dbmodel.status = request.status
            if request.usage is not None:
                dbmodel.usage = request.usage
            if request.created_vacancy_id is not None:
                vacancy = await Vacancy.find_one(
                    {
                        "_id": request.created_vacancy_id,
                        "deleted_at": None,
                    },
                )

                if vacancy is not None:
                    dbmodel.created_vacancy = vacancy

            dbmodel.updated_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.OperationValidateError("validation error") from e
        except protocol.OperationNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.UpdateOperationError("unknown error") from e

    @span(op="mongodb_repository", name="update_parse_candidate_operation")
    @override
    async def update_parse_candidate_operation(
        self,
        request: OperationRepositoryProtocol.UpdateParseCandidateOperationRequest,
    ) -> domain.ParseCandidateOperation:
        try:
            dbmodel = await ParseCandidateOperation.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("operation with id does not exist", operation_id=request.id)
                raise protocol.OperationNotFoundError("operation does not exist")
            if request.finished_at is not None:
                dbmodel.finished_at = request.finished_at
            if request.status is not None:
                dbmodel.status = request.status
            if request.usage is not None:
                dbmodel.usage = request.usage
            if request.created_candidate_id is not None:
                candidate = await Candidate.find_one(
                    {
                        "_id": request.created_candidate_id,
                        "deleted_at": None,
                    },
                )
                if candidate is not None:
                    dbmodel.created_candidate = candidate

            dbmodel.updated_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.OperationValidateError("validation error") from e
        except protocol.OperationNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.UpdateOperationError("unknown error") from e

    @span(op="mongodb_repository", name="update_generate_analysis_operation")
    @override
    async def update_generate_analysis_operation(
        self,
        request: OperationRepositoryProtocol.UpdateGenerateAnalysisOperationRequest,
    ) -> domain.GenerateAnalysisOperation:
        try:
            dbmodel = await GenerateAnalysisOperation.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("operation with id does not exist", operation_id=request.id)
                raise protocol.OperationNotFoundError("operation does not exist")
            if request.finished_at is not None:
                dbmodel.finished_at = request.finished_at
            if request.status is not None:
                dbmodel.status = request.status
            if request.usage is not None:
                dbmodel.usage = request.usage

            dbmodel.updated_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.OperationValidateError("validation error") from e
        except protocol.OperationNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.UpdateOperationError("unknown error") from e

    @span(op="mongodb_repository", name="delete_operation")
    @override
    async def delete_operation(self, request: OperationRepositoryProtocol.DeleteOperationRequest) -> domain.Operation:
        try:
            dbmodel = await Operation.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("operation with id does not exist", operation_id=request.id)
                raise protocol.OperationNotFoundError("operation does not exist")
            dbmodel.deleted_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            if not isinstance(dbmodel, ParseVacancyOperation | ParseCandidateOperation | GenerateAnalysisOperation):
                raise protocol.UnknownOperationTypeError(f"unknown operation type: {type(dbmodel)}")

            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.OperationValidateError("validation error") from e
        except protocol.OperationNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except protocol.UnknownOperationTypeError as e:
            log.error("failed with unknown type error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.DeleteOperationError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_operations")
    @override
    async def read_many_operations(
        self, request: OperationRepositoryProtocol.ReadManyOperationsRequest
    ) -> list[domain.Operation | None]:
        try:
            dbmodels = await Operation.find({"_id": {"$in": request.operation_ids}, "deleted_at": None}).to_list()
            mapping = {
                str(dbmodel.id): dbmodel.to_domain()
                if isinstance(dbmodel, ParseVacancyOperation | ParseCandidateOperation | GenerateAnalysisOperation)
                else None
                for dbmodel in dbmodels
            }
            return [mapping.get(str(dbmodel.id)) for dbmodel in dbmodels]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.OperationValidateError("validation error") from e
        except protocol.OperationRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadOperationError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_operations_by_user")
    @override
    async def read_many_operations_by_user(
        self, request: OperationRepositoryProtocol.ReadManyOperationsByUserRequest
    ) -> list[domain.ParseVacancyOperation | domain.ParseCandidateOperation | domain.GenerateAnalysisOperation]:
        try:
            operations = await Operation.find(
                {"user.$id": request.user_id, "deleted_at": None}, with_children=True
            ).to_list()
            for operation in operations:
                await operation.fetch_all_links()
            return [operation.to_domain() for operation in operations]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.ReadOperationError("validation error") from e
        except protocol.OperationRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadOperationError("unknown error") from e

    @span(op="mongodb_repository", name="create_user_profile")
    @override
    async def create_user_profile(self, request: UserRepositoryProtocol.CreateUserProfileRequest) -> domain.UserProfile:
        try:
            dbmodel = UserProfile(
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                deleted_at=None,
                email=request.email,
                name=request.name,
                password=request.password,
                thumbnail_url=request.thumbnail_url,
                tariff=request.tariff,
                tutorials=request.tutorials,
                projects=[],
            )
            dbmodel = await dbmodel.insert()

            if dbmodel.id is None:
                raise protocol.UserRepositoryError("user creation failed")

            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.UserValidateError("validation error") from e
        except protocol.UserRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.CreateUserError("unknown error") from e

    @span(op="mongodb_repository", name="read_user_profile")
    @override
    async def read_user_profile(self, request: UserRepositoryProtocol.ReadUserProfileRequest) -> domain.UserProfile:
        try:
            dbmodel = await UserProfile.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("user with id does not exist", user_id=request.id)
                raise protocol.UserNotFoundError("user does not exist")
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.UserValidateError("validation error") from e
        except protocol.UserNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadUserError("unknown error") from e

    @span(op="mongodb_repository", name="update_user_profile")
    @override
    async def update_user_profile(  # noqa: C901
        self, request: UserRepositoryProtocol.UpdateUserProfileRequest
    ) -> domain.UserProfile:
        try:
            dbmodel = await UserProfile.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("user with id does not exist", user_id=request.id)
                raise protocol.UserNotFoundError("user does not exist")
            if request.email is not None:
                dbmodel.email = request.email
            if request.name is not None:
                dbmodel.name = request.name
            if request.password is not None:
                dbmodel.password = request.password
            if request.thumbnail_url is not None:
                dbmodel.thumbnail_url = request.thumbnail_url
            if request.tariff is not None:
                dbmodel.tariff = request.tariff
            if request.tutorials is not None:
                dbmodel.tutorials = request.tutorials
            if request.projects is not None:
                dbmodel.projects = await Project.find({"_id": {"$in": request.projects}, "deleted_at": None}).to_list()
            dbmodel.updated_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.UserValidateError("validation error") from e
        except protocol.UserNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.UpdateUserError("unknown error") from e

    @span(op="mongodb_repository", name="delete_user_profile")
    @override
    async def delete_user_profile(self, request: UserRepositoryProtocol.DeleteUserProfileRequest) -> domain.UserProfile:
        try:
            dbmodel = await UserProfile.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("user with id does not exist", user_id=request.id)
                raise protocol.UserNotFoundError("user does not exist")
            dbmodel.deleted_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            return domain.UserProfile.model_validate(dbmodel, from_attributes=True)
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.UserValidateError("validation error") from e
        except protocol.UserNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.DeleteUserError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_user_profiles")
    @override
    async def read_many_user_profiles(
        self, request: UserRepositoryProtocol.ReadManyUserProfilesRequest
    ) -> list[domain.UserProfile | None]:
        try:
            dbmodels = await UserProfile.find({"_id": {"$in": request.user_ids}, "deleted_at": None}).to_list()
            await asyncio.gather(*[dbmodel.fetch_all_links() for dbmodel in dbmodels])
            mapping = {str(dbmodel.id): dbmodel.to_domain() for dbmodel in dbmodels}
            return [mapping.get(str(dbmodel.id)) for dbmodel in dbmodels]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.UserValidateError("validation error") from e
        except protocol.UserRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadUserError("unknown error") from e

    @span(op="mongodb_repository", name="read_user_profile_by_email")
    @override
    async def read_user_profile_by_email(
        self, request: UserRepositoryProtocol.ReadUserProfileByEmailRequest
    ) -> domain.UserProfile:
        try:
            dbmodel = await UserProfile.find_one({"email": request.email, "deleted_at": None})
            if dbmodel is None:
                log.error("user with email does not exist", email=request.email)
                raise protocol.UserNotFoundError("user does not exist")

            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.UserValidateError("validation error") from e
        except protocol.UserNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadUserError("unknown error") from e

    @span(op="mongodb_repository", name="read_all_user_profiles")
    @override
    async def read_all_user_profiles(self) -> list[domain.UserProfile]:
        try:
            dbmodels = await UserProfile.find({"deleted_at": None}).to_list()
            _ = await asyncio.gather(*[dbmodel.fetch_all_links() for dbmodel in dbmodels])
            return [dbmodel.to_domain() for dbmodel in dbmodels]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.UserValidateError("validation error") from e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadUserError("unknown error") from e

    @span(op="mongodb_repository", name="create_customer_contact")
    @override
    async def create_customer_contact(
        self, request: CustomerContactRepositoryProtocol.CreateCustomerContactRequest
    ) -> domain.CustomerContact:
        try:
            dbmodel = CustomerContact(
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                deleted_at=None,
                name=request.name,
                contact=request.contact,
                number_employees=request.number_employees,
            )
            dbmodel = await dbmodel.insert()

            if dbmodel.id is None:
                raise protocol.CustomerContactRepositoryError("customer contact creation failed")

            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CustomerContactValidateError("validation error") from e
        except protocol.CustomerContactRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.CreateCustomerContactError("unknown error") from e

    @span(op="mongodb_repository", name="read_customer_contact")
    @override
    async def read_customer_contact(
        self, request: CustomerContactRepositoryProtocol.ReadCustomerContactRequest
    ) -> domain.CustomerContact:
        try:
            dbmodel = await CustomerContact.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("customer contact with id does not exist", customer_contact_id=request.id)
                raise protocol.CustomerContactNotFoundError("customer contact does not exist")
            return domain.CustomerContact.model_validate(dbmodel, from_attributes=True)
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CustomerContactValidateError("validation error") from e
        except protocol.CustomerContactNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadCustomerContactError("unknown error") from e

    @span(op="mongodb_repository", name="update_customer_contact")
    @override
    async def update_customer_contact(
        self, request: CustomerContactRepositoryProtocol.UpdateCustomerContactRequest
    ) -> domain.CustomerContact:
        try:
            dbmodel = await CustomerContact.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("customer contact with id does not exist", customer_contact_id=request.id)
                raise protocol.CustomerContactNotFoundError("customer contact does not exist")
            if request.name is not None:
                dbmodel.name = request.name
            if request.contact is not None:
                dbmodel.contact = request.contact
            if request.number_employees is not None:
                dbmodel.number_employees = request.number_employees
            dbmodel.updated_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CustomerContactValidateError("validation error") from e
        except protocol.CustomerContactNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.UpdateCustomerContactError("unknown error") from e

    @span(op="mongodb_repository", name="delete_customer_contact")
    @override
    async def delete_customer_contact(
        self, request: CustomerContactRepositoryProtocol.DeleteCustomerContactRequest
    ) -> domain.CustomerContact:
        try:
            dbmodel = await CustomerContact.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("customer contact with id does not exist", customer_contact_id=request.id)
                raise protocol.CustomerContactNotFoundError("customer contact does not exist")
            dbmodel.deleted_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CustomerContactValidateError("validation error") from e
        except protocol.CustomerContactNotFoundError as e:
            log.error("failed with not found error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.DeleteCustomerContactError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_customer_contacts")
    @override
    async def read_many_customer_contacts(
        self,
        request: CustomerContactRepositoryProtocol.ReadManyCustomerContactsRequest,
    ) -> list[domain.CustomerContact | None]:
        try:
            dbmodels = await CustomerContact.find({
                "_id": {"$in": request.customer_contact_ids},
                "deleted_at": None,
            }).to_list()
            mapping = {
                str(dbmodel.id): domain.CustomerContact.model_validate(dbmodel, from_attributes=True)
                for dbmodel in dbmodels
            }
            return [mapping.get(str(dbmodel.id)) for dbmodel in dbmodels]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CustomerContactValidateError("validation error") from e
        except protocol.CustomerContactRepositoryError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadCustomerContactError("unknown error") from e

    @span(op="mongodb_repository", name="create_criterion")
    @override
    async def create_criterion(self, request: CriterionRepositoryProtocol.CreateCriterionRequest) -> domain.Criterion:
        try:
            vacancy = await Vacancy.find_one({"_id": request.vacancy_id, "deleted_at": None})
            if vacancy is None:
                log.error("vacancy with id does not exist", vacancy_id=request.vacancy_id)
                raise protocol.VacancyNotFoundError("vacancy does not exist")

            dbmodel = Criterion(
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                deleted_at=None,
                user=vacancy.user,
                project=vacancy.project,
                vacancy=vacancy,
                criterion=request.criterion,
                initial_weight=request.initial_weight,
                weight=request.weight,
                calculated=request.calculated,
            )
            dbmodel = await dbmodel.insert()
            if dbmodel.id is None:
                raise protocol.CreateCriterionError("criterion creation failed")
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CriterionValidateError("validation error") from e
        except protocol.VacancyNotFoundError as e:
            log.error("failed with vacancy not found", err=e)
            raise e
        except protocol.CreateCriterionError as e:
            log.error("failed with creation", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.CreateCriterionError("unknown error") from e

    @span(op="mongodb_repository", name="create_many_criteria")
    @override
    async def create_many_criteria(
        self, request: CriterionRepositoryProtocol.CreateManyCriteriaRequest
    ) -> list[domain.CriterionID]:
        try:
            vacancy = await Vacancy.find_one({"_id": request.vacancy_id, "deleted_at": None})
            if vacancy is None:
                log.error("vacancy with id does not exist", vacancy_id=request.vacancy_id)
                raise protocol.VacancyNotFoundError("vacancy does not exist")

            if not request.criteria:
                return []

            now = datetime.now(UTC)

            dbmodels = [
                Criterion(
                    created_at=now,
                    updated_at=now,
                    deleted_at=None,
                    user=vacancy.user,
                    project=vacancy.project,
                    vacancy=vacancy,
                    criterion=c.criterion,
                    initial_weight=c.initial_weight,
                    weight=0,
                    calculated=False,
                )
                for c in request.criteria
            ]

            inserted = await Criterion.insert_many(dbmodels)
            ids = inserted.inserted_ids or []

            if not ids or len(ids) != len(dbmodels) or any(_id is None for _id in ids):
                raise protocol.CreateCriterionError("criterion creation failed")

            return [domain.CriterionID(_id) for _id in ids]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CriterionValidateError("validation error") from e
        except protocol.VacancyNotFoundError as e:
            log.error("failed with vacancy not found", err=e)
            raise e
        except protocol.CreateCriterionError as e:
            log.error("failed with creation", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.CreateCriterionError("unknown error") from e

    @span(op="mongodb_repository", name="read_criterion")
    @override
    async def read_criterion(self, request: CriterionRepositoryProtocol.ReadCriterionRequest) -> domain.Criterion:
        try:
            dbmodel = await Criterion.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("criterion with id does not exist", criterion_id=request.id)
                raise protocol.CriterionNotFoundError("criterion does not exist")
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CriterionValidateError("validation error") from e
        except protocol.CriterionNotFoundError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadCriterionError("unknown error") from e

    @span(op="mongodb_repository", name="update_criterion")
    @override
    async def update_criterion(self, request: CriterionRepositoryProtocol.UpdateCriterionRequest) -> domain.Criterion:
        try:
            dbmodel = await Criterion.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("criterion with id does not exist", criterion_id=request.id)
                raise protocol.CriterionNotFoundError("criterion does not exist")
            if request.criterion is not None:
                dbmodel.criterion = request.criterion
            if request.initial_weight is not None:
                dbmodel.initial_weight = request.initial_weight
            if request.weight is not None:
                dbmodel.weight = request.weight
            if request.calculated is not None:
                dbmodel.calculated = request.calculated
            dbmodel.updated_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CriterionValidateError("validation error") from e
        except protocol.CriterionNotFoundError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.UpdateCriterionError("unknown error") from e

    @span(op="mongodb_repository", name="delete_criterion")
    @override
    async def delete_criterion(self, request: CriterionRepositoryProtocol.DeleteCriterionRequest) -> domain.Criterion:
        try:
            dbmodel = await Criterion.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("criterion with id does not exist", criterion_id=request.id)
                raise protocol.CriterionNotFoundError("criterion does not exist")
            dbmodel.deleted_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CriterionValidateError("validation error") from e
        except protocol.CriterionNotFoundError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.DeleteCriterionError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_criteria")
    @override
    async def read_many_criteria(
        self, request: CriterionRepositoryProtocol.ReadManyCriteriaRequest
    ) -> list[domain.Criterion | None]:
        try:
            db_models = await Criterion.find({"_id": {"$in": request.criterion_ids}, "deleted_at": None}).to_list()
            await asyncio.gather(*[db_model.fetch_all_links() for db_model in db_models])
            mapping = {str(db_model.id): db_model.to_domain() for db_model in db_models}
            return [mapping.get(str(db_model.id)) for db_model in db_models]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CriterionValidateError("validation error") from e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadCriterionError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_criteria_by_vacancy")
    @override
    async def read_many_criteria_by_vacancy(
        self, request: CriterionRepositoryProtocol.ReadManyCriteriaByVacancyRequest
    ) -> list[domain.Criterion]:
        try:
            db_models = await Criterion.find({"vacancy.$id": request.vacancy_id, "deleted_at": None}).to_list()
            await asyncio.gather(*[db_model.fetch_all_links() for db_model in db_models])
            return [db_model.to_domain() for db_model in db_models]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.CriterionValidateError("validation error") from e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadCriterionError("unknown error") from e

    @span(op="mongodb_repository", name="create_stop_factor")
    @override
    async def create_stop_factor(
        self, request: StopFactorRepositoryProtocol.CreateStopFactorRequest
    ) -> domain.StopFactor:
        try:
            vacancy = await Vacancy.find_one({"_id": request.vacancy_id, "deleted_at": None})
            if vacancy is None:
                log.error("vacancy with id does not exist", vacancy_id=request.vacancy_id)
                raise protocol.VacancyNotFoundError("vacancy does not exist")

            dbmodel = StopFactor(
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                deleted_at=None,
                user=vacancy.user,
                project=vacancy.project,
                vacancy=vacancy,
                stop_factor=request.stop_factor,
                initial_weight=request.initial_weight,
            )
            dbmodel = await dbmodel.insert()
            if dbmodel.id is None:
                raise protocol.CreateStopFactorError("stop factor creation failed")
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.StopFactorValidateError("validation error") from e
        except protocol.VacancyNotFoundError as e:
            log.error("failed with vacancy not found", err=e)
            raise e
        except protocol.CreateStopFactorError as e:
            log.error("failed with creation", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.CreateStopFactorError("unknown error") from e

    @span(op="mongodb_repository", name="create_many_stop_factors")
    @override
    async def create_many_stop_factors(
        self, request: StopFactorRepositoryProtocol.CreateManyStopFactorsRequest
    ) -> list[domain.StopFactorID]:
        try:
            vacancy = await Vacancy.find_one({"_id": request.vacancy_id, "deleted_at": None})
            if vacancy is None:
                log.error("vacancy with id does not exist", vacancy_id=request.vacancy_id)
                raise protocol.VacancyNotFoundError("vacancy does not exist")

            if not request.stop_factors:
                return []

            now = datetime.now(UTC)

            dbmodels = [
                StopFactor(
                    created_at=now,
                    updated_at=now,
                    deleted_at=None,
                    user=vacancy.user,
                    project=vacancy.project,
                    vacancy=vacancy,
                    stop_factor=c.stop_factor,
                    initial_weight=c.initial_weight,
                )
                for c in request.stop_factors
            ]

            inserted = await StopFactor.insert_many(dbmodels)
            ids = inserted.inserted_ids or []

            if not ids or len(ids) != len(dbmodels) or any(_id is None for _id in ids):
                raise protocol.CreateStopFactorError("stop factor creation failed")

            return [domain.StopFactorID(_id) for _id in ids]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.StopFactorValidateError("validation error") from e
        except protocol.VacancyNotFoundError as e:
            log.error("failed with vacancy not found", err=e)
            raise e
        except protocol.CreateStopFactorError as e:
            log.error("failed with creation", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.CreateStopFactorError("unknown error") from e

    @span(op="mongodb_repository", name="read_stop_factor")
    @override
    async def read_stop_factor(self, request: StopFactorRepositoryProtocol.ReadStopFactorRequest) -> domain.StopFactor:
        try:
            dbmodel = await StopFactor.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("stop factor with id does not exist", criterion_id=request.id)
                raise protocol.StopFactorNotFoundError("stop factor does not exist")
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.StopFactorValidateError("validation error") from e
        except protocol.StopFactorNotFoundError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadStopFactorError("unknown error") from e

    @span(op="mongodb_repository", name="update_stop_factor")
    @override
    async def update_stop_factor(
        self, request: StopFactorRepositoryProtocol.UpdateStopFactorRequest
    ) -> domain.StopFactor:
        try:
            dbmodel = await StopFactor.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("stop factor with id does not exist", criterion_id=request.id)
                raise protocol.StopFactorNotFoundError("stop factor does not exist")
            if request.stop_factor is not None:
                dbmodel.stop_factor = request.stop_factor
            if request.initial_weight is not None:
                dbmodel.initial_weight = request.initial_weight
            dbmodel.updated_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.StopFactorValidateError("validation error") from e
        except protocol.StopFactorNotFoundError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.UpdateStopFactorError("unknown error") from e

    @span(op="mongodb_repository", name="delete_stop_factor")
    @override
    async def delete_stop_factor(
        self, request: StopFactorRepositoryProtocol.DeleteStopFactorRequest
    ) -> domain.StopFactor:
        try:
            dbmodel = await StopFactor.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("stop factor with id does not exist", criterion_id=request.id)
                raise protocol.StopFactorNotFoundError("stop factor does not exist")
            dbmodel.deleted_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.StopFactorValidateError("validation error") from e
        except protocol.StopFactorNotFoundError as e:
            log.error("failed with error", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.DeleteStopFactorError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_stop_factors")
    @override
    async def read_many_stop_factors(
        self, request: StopFactorRepositoryProtocol.ReadManyStopFactorsRequest
    ) -> list[domain.StopFactor | None]:
        try:
            db_models = await StopFactor.find({"_id": {"$in": request.stop_factor_ids}, "deleted_at": None}).to_list()
            await asyncio.gather(*[db_model.fetch_all_links() for db_model in db_models])
            mapping = {str(db_model.id): db_model.to_domain() for db_model in db_models}
            return [mapping.get(str(db_model.id)) for db_model in db_models]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.StopFactorValidateError("validation error") from e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadStopFactorError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_stop_factors_by_vacancy")
    @override
    async def read_many_stop_factors_by_vacancy(
        self, request: StopFactorRepositoryProtocol.ReadManyStopFactorsByVacancyRequest
    ) -> list[domain.StopFactor]:
        try:
            db_models = await StopFactor.find({"vacancy.$id": request.vacancy_id, "deleted_at": None}).to_list()
            await asyncio.gather(*[db_model.fetch_all_links() for db_model in db_models])
            return [db_model.to_domain() for db_model in db_models]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.StopFactorValidateError("validation error") from e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadStopFactorError("unknown error") from e

    @span(op="mongodb_repository", name="create_oauth2")
    @override
    async def create_oauth2_profile(
        self, request: OAuth2RepositoryProtocol.CreateOAuth2Request
    ) -> domain.OAuth2Profile:
        try:
            user = await UserProfile.find_one({"_id": request.user_id, "deleted_at": None})
            if user is None:
                log.error("user with id does not exist", user_id=request.user_id)
                raise protocol.UserNotFoundError("user does not exist")

            oauth2 = await OAuth2Profile.find_one({
                "user.$id": request.user_id,
                "source": request.source,
                "deleted_at": None,
            })
            if oauth2 is not None:
                log.info(
                    "oauth2 with user_id and source already exists", user_id=request.user_id, source=request.source
                )
                oauth2 = await oauth2.save()
                await oauth2.fetch_all_links()
                return oauth2.to_domain()

            dbmodel = OAuth2Profile(
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                deleted_at=None,
                user=user,
                source=request.source,
                token=request.token,
            )
            dbmodel = await dbmodel.insert()
            if dbmodel.id is None:
                raise protocol.CreateOAuth2Error("oauth2 creation failed")
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.OAuth2ValidateError("validation error") from e
        except protocol.UserNotFoundError as e:
            log.error("failed with user not found", err=e)
            raise e
        except protocol.CreateOAuth2Error as e:
            log.error("failed with creation", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.CreateOAuth2Error("unknown error") from e

    @span(op="mongodb_repository", name="read_oauth2")
    @override
    async def read_oauth2_profile(self, request: OAuth2RepositoryProtocol.ReadOAuth2Request) -> domain.OAuth2Profile:
        try:
            dbmodel = await OAuth2Profile.find_one({
                "user.$id": request.user_id,
                "source": request.source,
                "deleted_at": None,
            })
            if dbmodel is None:
                log.error(
                    "oauth2 with user_id and source does not exist", user_id=request.user_id, source=request.source
                )
                raise protocol.OAuth2NotFoundError("oauth2 does not exist")
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.OAuth2ValidateError("validation error") from e
        except protocol.OAuth2NotFoundError as e:
            log.error("failed with oauth2 not found", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadOAuth2Error("unknown error") from e

    @span(op="mongodb_repository", name="update_oauth2")
    @override
    async def update_oauth2_profile(
        self, request: OAuth2RepositoryProtocol.UpdateOAuth2Request
    ) -> domain.OAuth2Profile:
        try:
            dbmodel = await OAuth2Profile.find_one({
                "user.$id": request.user_id,
                "source": request.source,
                "deleted_at": None,
            })
            if dbmodel is None:
                log.error(
                    "oauth2 with user_id and source does not exist", user_id=request.user_id, source=request.source
                )
                raise protocol.OAuth2NotFoundError("oauth2 does not exist")
            if request.token is not None:
                dbmodel.token = request.token
            dbmodel.updated_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.OAuth2ValidateError("validation error") from e
        except protocol.OAuth2NotFoundError as e:
            log.error("failed with oauth2 not found", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.UpdateOAuth2Error("unknown error") from e

    @span(op="mongodb_repository", name="delete_oauth2")
    @override
    async def delete_oauth2_profile(
        self, request: OAuth2RepositoryProtocol.DeleteOAuth2Request
    ) -> domain.OAuth2Profile:
        try:
            dbmodel = await OAuth2Profile.find_one({
                "user.$id": request.user_id,
                "source": request.source,
                "deleted_at": None,
            })
            if dbmodel is None:
                log.error(
                    "oauth2 with user_id and source does not exist", user_id=request.user_id, source=request.source
                )
                raise protocol.OAuth2NotFoundError("oauth2 does not exist")
            dbmodel.deleted_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.OAuth2ValidateError("validation error") from e
        except protocol.OAuth2NotFoundError as e:
            log.error("failed with oauth2 not found", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.DeleteOAuth2Error("unknown error") from e

    @span(op="mongodb_repository", name="read_many_oauth2_profiles")
    @override
    async def read_many_oauth2_profiles(
        self, request: OAuth2RepositoryProtocol.ReadManyOAuth2Request
    ) -> list[domain.OAuth2Profile]:
        try:
            db_models = await OAuth2Profile.find({"user.$id": request.user_id, "deleted_at": None}).to_list()
            await asyncio.gather(*[db_model.fetch_all_links() for db_model in db_models])
            return [db_model.to_domain() for db_model in db_models]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.OAuth2ValidateError("validation error") from e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadOAuth2Error("unknown error") from e

    @span(op="mongodb_repository", name="create_statistics")
    @override
    async def create_statistics(
        self, request: StatisticsRepositoryProtocol.CreateStatisticsRequest
    ) -> domain.Statistics:
        try:
            vacancy = await Vacancy.find_one({"_id": request.vacancy_id, "deleted_at": None})
            if vacancy is None:
                log.error("vacancy with id does not exist", vacancy_id=request.vacancy_id)
                raise protocol.VacancyNotFoundError("user does not exist")

            statistics = await Statistics.find_one({"vacancy.$id": request.vacancy_id, "deleted_at": None})
            if statistics is not None:
                log.error("statistics with vacancy_id already exists", vacancy_id=request.vacancy_id)
                raise protocol.StatisticsWithVacancyAlreadyExistsError("statistics with vacancy_id already exists")

            dbmodel = Statistics(
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                deleted_at=None,
                user=vacancy.user,
                project=vacancy.project,
                vacancy=vacancy,
                project_statistics=request.project_statistics,
                vacancy_statistics=request.vacancy_statistics,
                score_statistics=request.score_statistics,
                stage_statistics=request.stage_statistics,
                criterion_stop_factor_status_statistics=request.criterion_stop_factor_status_statistics,
                date_increase_statistics=request.date_increase_statistics,
                salary_statistics=request.salary_statistics,
            )
            dbmodel = await dbmodel.insert()
            if dbmodel.id is None:
                raise protocol.CreateStatisticsError("statistics creation failed")
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except protocol.StatisticsWithVacancyAlreadyExistsError as e:
            log.error("failed with already existing statistics for vacancy", err=e)
            raise e
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.StatisticsValidateError("validation error") from e
        except protocol.VacancyNotFoundError as e:
            log.error("failed with vacancy not found", err=e)
            raise e
        except protocol.CreateStatisticsError as e:
            log.error("failed with creation", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.CreateStatisticsError("unknown error") from e

    @span(op="mongodb_repository", name="read_statistics_by_vacancy")
    @override
    async def read_statistics_by_vacancy(
        self, request: StatisticsRepositoryProtocol.ReadStatisticsByVacancyRequest
    ) -> domain.Statistics:
        try:
            dbmodel = await Statistics.find_one({"vacancy.$id": request.vacancy_id, "deleted_at": None})
            if dbmodel is None:
                log.error("statistics with vacancy_id does not exist", vacancy_id=request.vacancy_id)
                raise protocol.StatisticsNotFoundError("statistics does not exist")
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.StatisticsValidateError("validation error") from e
        except protocol.StatisticsNotFoundError as e:
            log.error("failed with statistics not found", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadStatisticsError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_statistics_by_project")
    @override
    async def read_many_statistics_by_project(
        self, request: StatisticsRepositoryProtocol.ReadManyStatisticsByProjectRequest
    ) -> list[domain.Statistics]:
        try:
            db_models = await Statistics.find({"project.$id": request.project_id, "deleted_at": None}).to_list()
            await asyncio.gather(*[db_model.fetch_all_links() for db_model in db_models])
            return [db_model.to_domain() for db_model in db_models]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.StatisticsValidateError("validation error") from e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadStatisticsError("unknown error") from e

    @span(op="mongodb_repository", name="update_statistics_by_vacancy")
    @override
    async def update_or_create_statistics_by_vacancy(  # noqa: C901
        self, request: StatisticsRepositoryProtocol.UpdateStatisticsByVacancyRequest
    ) -> domain.Statistics:
        try:
            dbmodel = await Statistics.find_one({"vacancy.$id": request.vacancy_id, "deleted_at": None})
            if dbmodel is None:
                log.info("statistics with vacancy_id does not exist", vacancy_id=request.vacancy_id)

                if request.project_statistics is None:
                    project_statistics = domain.ProjectStatistics(
                        total_candidates=0,
                        total_vacancies=0,
                        active_vacancies=0,
                    )
                else:
                    project_statistics = request.project_statistics

                if request.vacancy_statistics is None:
                    vacancy_statistics = domain.VacancyCandidatesStatistics(
                        total_candidates=0,
                        total_today_increase=0,
                        platform_candidates=0,
                        platform_today_increase=0,
                        hh_candidates=0,
                        hh_today_increase=0,
                        total_dirty_candidates=0,
                        dirty_today_increase=0,
                    )
                else:
                    vacancy_statistics = request.vacancy_statistics

                if request.score_statistics is None:
                    score_statistics = domain.CandidateScoreStatistics(statistics={})
                else:
                    score_statistics = request.score_statistics

                if request.stage_statistics is None:
                    stage_statistics = domain.CandidateStageStatistics(statistics={})
                else:
                    stage_statistics = request.stage_statistics

                if request.criterion_stop_factor_status_statistics is None:
                    criterion_stop_factor_status_statistics = domain.CandidateCriterionStopFactorStatusStatistics(
                        criterion_status_statistics={},
                        stop_factor_status_statistics={},
                    )
                else:
                    criterion_stop_factor_status_statistics = request.criterion_stop_factor_status_statistics

                if request.date_increase_statistics is None:
                    date_increase_statistics = domain.CandidateDateIncreaseStatistics(statistics={})
                else:
                    date_increase_statistics = request.date_increase_statistics

                if request.salary_statistics is None:
                    salary_statistics = domain.CandidateSalaryStatistics(
                        currency=CurrencyISO4217("RUB"), count=0, average=0, median=0
                    )
                else:
                    salary_statistics = request.salary_statistics

                response = await self.create_statistics(
                    StatisticsRepositoryProtocol.CreateStatisticsRequest(
                        vacancy_id=request.vacancy_id,
                        project_statistics=project_statistics,
                        vacancy_statistics=vacancy_statistics,
                        score_statistics=score_statistics,
                        stage_statistics=stage_statistics,
                        criterion_stop_factor_status_statistics=criterion_stop_factor_status_statistics,
                        date_increase_statistics=date_increase_statistics,
                        salary_statistics=salary_statistics,
                    )
                )
                return response

            if request.project_statistics is not None:
                dbmodel.project_statistics = request.project_statistics
            if request.vacancy_statistics is not None:
                dbmodel.vacancy_statistics = request.vacancy_statistics
            if request.score_statistics is not None:
                dbmodel.score_statistics = request.score_statistics
            if request.stage_statistics is not None:
                dbmodel.stage_statistics = request.stage_statistics
            if request.criterion_stop_factor_status_statistics is not None:
                dbmodel.criterion_stop_factor_status_statistics = request.criterion_stop_factor_status_statistics
            if request.date_increase_statistics is not None:
                dbmodel.date_increase_statistics = request.date_increase_statistics
            if request.salary_statistics is not None:
                dbmodel.salary_statistics = request.salary_statistics

            dbmodel.updated_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()

        except (
            protocol.StatisticsWithVacancyAlreadyExistsError,
            protocol.StatisticsValidateError,
            protocol.VacancyNotFoundError,
            protocol.CreateStatisticsError,
        ) as e:
            raise e

        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.StatisticsValidateError("validation error") from e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.UpdateStatisticsError("unknown error") from e

    @span(op="mongodb_repository", name="delete_statistics")
    @override
    async def delete_statistics(
        self, request: StatisticsRepositoryProtocol.DeleteStatisticsRequest
    ) -> domain.Statistics:
        try:
            dbmodel = await Statistics.find_one({"_id": request.id, "deleted_at": None})
            if dbmodel is None:
                log.error("statistics with id does not exist", id=request.id)
                raise protocol.StatisticsNotFoundError("statistics does not exist")
            dbmodel.deleted_at = datetime.now(UTC)
            dbmodel = await dbmodel.save()
            await dbmodel.fetch_all_links()
            return dbmodel.to_domain()
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.StatisticsValidateError("validation error") from e
        except protocol.StatisticsNotFoundError as e:
            log.error("failed with statistics not found", err=e)
            raise e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.DeleteStatisticsError("unknown error") from e

    @span(op="mongodb_repository", name="read_many_statistics_by_vacancies")
    @override
    async def read_many_statistics_by_vacancies(
        self, request: StatisticsRepositoryProtocol.ReadManyStatisticsByVacanciesRequest
    ) -> list[domain.Statistics | None]:
        try:
            db_models = await Statistics.find({
                "vacancy.$id": {"$in": request.vacancy_ids},
                "deleted_at": None,
            }).to_list()
            await asyncio.gather(*[db_model.fetch_all_links() for db_model in db_models])
            mapping = {str(db_model.id): db_model.to_domain() for db_model in db_models}
            return [mapping.get(str(db_model.id)) for db_model in db_models]
        except pydantic.ValidationError as e:
            log.error("failed with validation error", err=e)
            raise protocol.StatisticsValidateError("validation error") from e
        except Exception as e:
            log.error("failed with unknown error", err=e)
            raise protocol.ReadStatisticsError("unknown error") from e
