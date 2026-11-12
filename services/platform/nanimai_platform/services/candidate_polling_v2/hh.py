import asyncio
import random
import string
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import structlog
from jinja2 import Template
from pydantic import BaseModel, HttpUrl
from pydantic_extra_types.currency_code import ISO4217 as CurrencyISO4217

from nanimai_platform import domain
from nanimai_platform.domain.candidate.candidate import Candidate
from nanimai_platform.protocols.external.candidate_polling import CandidatePollingProtocol as protocol
from nanimai_platform.protocols.external.candidate_polling import MoveToCollectionEnum
from nanimai_platform.protocols.external.vacancy_importer import VacancyImporterProtocol
from nanimai_platform.services.cache import Cache, Key, Keyspace
from nanimai_platform.services.candidate.service import CandidateService
from nanimai_platform.services.llm.service import LLMService
from nanimai_platform.services.oauth2 import OAuth2Service
from nanimai_platform.services.user_profile.service import UserService
from nanimai_platform.services.vacancy import VacancyService
from nanimai_platform.utils import NTDict
from nanimai_platform.utils.asyncio_background import launch_background
from nanimai_platform.utils.logging_span import span

with open(Path(__file__).parent / "hh_template.j2") as f:
    CANDIDATE_RESUME_TEMPLATE = Template(f.read())  # noqa: E501


log = structlog.stdlib.get_logger("app.services.candidate_polling_v2.hh")


class HHCandidatePollingV2Service:
    def __init__(
        self,
        candidate_service: CandidateService,
        llm_service: LLMService,
        user_service: UserService,
        oauth2_service: OAuth2Service,
        vacancy_service: VacancyService,
        cache: Cache,
        hh_candidate_polling_adapter: protocol,
        hh_vacancy_import_adapter: VacancyImporterProtocol,
    ):
        self._candidate_service = candidate_service
        self._llm_service = llm_service
        self._user_service = user_service
        self._oauth2_service = oauth2_service
        self._vacancy_service = vacancy_service
        self._cache = cache
        self._ks = Keyspace("candidate_polling_v2_service")
        self._hh_candidate_polling_adapter = hh_candidate_polling_adapter
        self._hh_vacancy_import_adapter = hh_vacancy_import_adapter
        self._sleep_between_vacancies_sec = 10
        self._sleep_worker_sec = 300
        self._full_resume_expire_in = timedelta(days=1)

    @span(op="candidate_polling_v2_hh", name="get_hh_vacancy_id")
    def _get_hh_vacancy_id(self, vacancy: domain.Vacancy) -> str | None:
        if (
            vacancy.publication.hh.state != domain.PublicationStatusEnum.PUBLISHED
            or vacancy.publication.hh.publication_id is None
        ):
            return None

        return vacancy.publication.hh.publication_id

    @span(op="candidate_polling_v2_hh", name="generate_candidate_resume")
    def _generate_candidate_resume(self, resume: NTDict) -> str:
        return CANDIDATE_RESUME_TEMPLATE.render(**resume.dict(), current_date=datetime.now().strftime("%Y-%m-%d"))

    @staticmethod
    def _map_hh_to_iso_currency(currency: str) -> CurrencyISO4217:
        currency_mapping = {
            # Azerbaijani manat
            "AZM": "AZN",
            "AZN": "AZN",
            # Belarusian ruble
            "BYR": "BYN",
            "BYN": "BYN",
            # Euro
            "EUR": "EUR",
            # Georgian lari
            "GEL": "GEL",
            # Kyrgyzstani som
            "KGS": "KGS",
            # Soviet Union ruble
            "SUR": "RUB",
            # Kazakhstani tenge
            "KZT": "KZT",
            # Russian ruble
            "RUR": "RUB",
            "RUB": "RUB",
            # Ukrainian hryvnia
            "UAH": "UAH",
            # Ukrainian karbovanets
            "UAK": "UAK",
            # USD
            "USD": "USD",
            # Uzbekistani sum
            "UZS": "UZS",
        }
        return CurrencyISO4217(currency_mapping.get(currency, "RUB"))

    @span(op="candidate_polling_v2_hh", name="generate_create_candidate_requests")
    async def _generate_create_candidate_requests(  # noqa: C901
        self,
        vacancy: domain.Vacancy,
        candidates: list[NTDict],
        access_token: str,
    ) -> list[CandidateService.CreateCandidateRequest]:
        resulting_list: list[CandidateService.CreateCandidateRequest] = []

        cache_dict: dict[str, NTDict] = {}

        for candidate in candidates:
            try:
                resume = candidate.getd("resume")
                resume_id = candidate.getd("resume").getv("id", None)
                if resume_id is None:
                    log.error("Failed to retrieve resume id", candidate=candidate)
                    continue

                if (full_resume := await self._cache.get(self._resume_key(str(resume_id)))) is not None:
                    log.info("retrieved full resume from cache", resume_id=resume_id)
                else:
                    full_resume = await self._hh_candidate_polling_adapter.retrieve_full_resume(
                        protocol.RetrieveFullResumeRequest(
                            resume_id=resume_id,
                            access_token=access_token,
                        )
                    )
                    log.info("retrieved full resume from hh", resume_id=resume_id)
                phone = None
                email = None
                if full_resume:
                    cache_dict[str(resume_id)] = full_resume
                    for contact in full_resume.getv("contact", []):
                        if phone is not None and email is not None:
                            break

                        contact = NTDict(contact)
                        if contact.getd("type").getv("id", "") == "cell":
                            phone = contact.getd("value").getv("formatted", None)
                            continue

                        if contact.getd("type").getv("id", "") == "email":
                            email = contact.getv("value", None)
                            continue

                resulting_list.append(
                    CandidateService.CreateCandidateRequest(
                        user_id=vacancy.user_id,
                        project_id=vacancy.project_id,
                        vacancy_id=vacancy.id,
                        resume=self._generate_candidate_resume(full_resume or resume),
                        name=f"{
                            resume.getv(
                                'first_name',
                                f'Кандидат <C_{
                                    candidate.getv("id", random.choices(string.ascii_lowercase + string.digits, k=6))
                                }>',
                            )
                        } {resume.getv('last_name', '')}".strip(),
                        city=resume.getd("area").getv("name", None),
                        country=None,
                        phone_number=phone,
                        email=email,
                        website=full_resume.getv("alternate_url", None),
                        experience=resume.getd("total_experience").getv("months", 0),
                        expected_salary=domain.ExpectedSalary(
                            currency=self._map_hh_to_iso_currency(  # type: ignore
                                resume.getd("salary").getv("currency", "RUB")
                            ),
                            value=resume.getd("salary").getv("amount", 0),
                        )
                        if resume.getd("salary").getv("amount", 0) != 0
                        else None,
                        notes="",
                        dirty=False,
                        source=domain.CandidateSourceEnum.HH,
                        skills=[domain.Skill(title=skill) for skill in full_resume.getv("skill_set", [])],
                        status=domain.VacancyStageEnum.MAGIC_AI,
                        analyses=[],
                    )
                )
            except Exception as e:
                log.error(
                    "Failed to generate create candidate request",
                    candidate=candidate,
                    error=str(e),
                    error_type=type(e).__name__,
                    traceback=traceback.format_exc(),
                )
                continue

        @launch_background
        async def update_cache() -> None:
            for resume_id, full_resume in cache_dict.items():
                await self._cache.set(self._resume_key(resume_id), full_resume, expire=self._full_resume_expire_in)

        update_cache()

        return resulting_list

    class PollNewCandidatesRequest(BaseModel):
        vacancy: domain.Vacancy
        hh_vacancy_id: str
        trace_id: str

    @span(op="candidate_polling_v2_hh", name="poll_new_candidates")
    async def _poll_new_candidates(self, request: PollNewCandidatesRequest) -> list[domain.Candidate]:
        try:
            """Poll HeadHunter API for new candidates for a vacancy"""
            clog = log.bind(trace_id=request.trace_id)
            vacancy = request.vacancy

            # Сейчас оставляем, но в будущем будем это убирать
            user = await self._user_service.read(UserService.ReadUserProfileRequest(id=vacancy.user_id))
            if user.tariff.analysis_used >= user.tariff.analysis_total:
                clog.info("user has reached analysis limit", user_id=vacancy.user_id)
                return []

            # https://github.com/hhru/api/blob/master/docs/employer_negotiations.md#flow

            oauth2 = await self._oauth2_service.retrieve_token(
                OAuth2Service.RetrieveTokenRequest(user_id=vacancy.user_id, source=domain.Oauth2SourceEnum.HH)
            )
            access_token = oauth2.token.access_token

            candidates_hh = await self._hh_candidate_polling_adapter.retrieve_unprocessed_candidates(
                protocol.RetrieveUnprocessedCandidatesRequest(
                    ext_api_vacancy_id=request.hh_vacancy_id,
                    access_token=access_token,
                )
            )

            if candidates_hh is None:
                clog.info("failed to retrieve candidates", vacancy_id=vacancy.id)
                return []
            clog.info("retrieved candidates", candidates_count=len(candidates_hh))

            for candidate in candidates_hh:
                await self._hh_candidate_polling_adapter.move_candidate_to_collection(
                    item=candidate,
                    move_to=MoveToCollectionEnum.CONSIDER,
                    access_token=access_token,
                )
            clog.info("move candidates to consider on HH", candidates_count=len(candidates_hh))

            requests = await self._generate_create_candidate_requests(vacancy, candidates_hh, access_token)
            clog.info("generated create candidate requests", requests_count=len(requests))

            clog.info("creating candidates", requests_count=len(requests))

            candidates_db: list[Candidate] = []
            for request in requests:
                try:
                    candidates_db.append(await self._candidate_service.create(request))
                except Exception as e:
                    log.error(
                        "Failed to poll candidates by vacancy",
                        error=str(e),
                        error_type=type(e).__name__,
                        traceback=traceback.format_exc(),
                    )
                    continue
            clog.info("created candidates", candidates_count=len(candidates_db))

            return candidates_db
        except Exception as e:
            log.error(
                "Failed to poll candidates by vacancy",
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )
            return []

    class AnalyzeCandidatesRequest(BaseModel):
        vacancy: domain.Vacancy
        candidates: list[domain.Candidate]
        trace_id: str

    @span(op="candidate_polling_v2_hh", name="analyze_candidates")
    async def _analyze_candidates(self, request: AnalyzeCandidatesRequest) -> int:
        try:
            clog = log.bind(trace_id=request.trace_id)

            # old analysis without criteria and stop-factors
            llm_request_max = len(request.candidates)
            llm_request_count = 0
            clog.info("generating LLM tasks", llm_requests_count=llm_request_max)

            for candidate in request.candidates:
                try:
                    llm_request = LLMService.NewAnalyzeOperationRequest(
                        request.vacancy.user_id, candidate.id, request.vacancy.id
                    )
                    await self._llm_service.new_analyze_operation(llm_request)
                    llm_request_count += 1
                except Exception as e:
                    log.error(
                        "Failed to analyze candidates",
                        error=str(e),
                        error_type=type(e).__name__,
                        traceback=traceback.format_exc(),
                    )
                    continue
            clog.info("generated LLM tasks", llm_requests_count=llm_request_count)

            # in new way we can provide request with user_id, candidate_id and vacancy id
            # where criteria and stop-factors are going to be retrieved by vacancy_id,
            # and llm will analyze candidates by criteria and stop-factors
            return llm_request_count

        except Exception as e:
            log.error(
                "Failed to analyze candidates",
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )
            return 0

    @span(op="candidate_polling_v2_hh", name="run_worker")
    async def run_worker(self) -> None:
        try:
            log.info("polling vacancies")
            vacancies = await self._vacancy_service.read_many_published(
                VacancyService.ReadManyPublishedVacanciesRequest(source=domain.VacancyPublicationSourceEnum.HH)
            )
            log.info("vacancies polled", count=len(vacancies))

            for vacancy in vacancies:
                if vacancy.status == domain.VacancyStatus.ARCHIVED:
                    continue

                if (hh_vacancy_id := self._get_hh_vacancy_id(vacancy)) is None:
                    continue
                trace_id = uuid4().hex
                clog = log.bind(trace_id=trace_id)

                hh_vacancy = await self._hh_vacancy_import_adapter.import_vacancy(
                    VacancyImporterProtocol.ImportVacancyRequest(
                        url=HttpUrl(f"https://hh.ru/vacancy/{hh_vacancy_id}"),
                        user_id=vacancy.user_id,
                    )
                )

                if hh_vacancy.status == domain.VacancyStatus.ARCHIVED:
                    continue

                clog.info("polling new candidates", vacancy_id=vacancy.id)
                result = await self._poll_new_candidates(
                    self.PollNewCandidatesRequest(
                        vacancy=vacancy,
                        hh_vacancy_id=hh_vacancy_id,
                        trace_id=trace_id,
                    )
                )
                clog.info("polled new candidates", vacancy_id=vacancy.id, candidates_count=len(result))

                clog.info("analyzing new candidates", vacancy_id=vacancy.id, candidate_count=len(result))
                analysis_count = await self._analyze_candidates(
                    self.AnalyzeCandidatesRequest(
                        vacancy=vacancy,
                        candidates=result,
                        trace_id=trace_id,
                    )
                )
                clog.info("analyzed new candidates", vacancy_id=vacancy.id, analysis_count=analysis_count)

                clog.info(f"sleeping {self._sleep_between_vacancies_sec} seconds")
                await asyncio.sleep(self._sleep_between_vacancies_sec)

            log.info(f"sleeping {self._sleep_worker_sec} seconds")
            await asyncio.sleep(self._sleep_worker_sec)

        except Exception as e:
            log.error(
                "Failed to analyze candidates",
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )

    # ===

    def _resume_key(self, resume_id: str) -> Key:
        return self._ks.key("id", str(resume_id))
