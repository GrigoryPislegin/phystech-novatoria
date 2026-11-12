import asyncio
import functools
import random
import string
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol, TypeVar
from uuid import uuid4

import hhsdk  # type: ignore[import-untyped]
import httpx
import structlog
from jinja2 import Template

from nanimai_platform import domain
from nanimai_platform.protocols.internal.file_storage.protocol import FileStorageProtocol
from nanimai_platform.services.candidate.service import CandidateService
from nanimai_platform.services.llm.service import LLMService
from nanimai_platform.services.user_profile.service import UserService
from nanimai_platform.utils.logging_span import span

with open(Path(__file__).parent / "template.j2") as f:
    CANDIDATE_RESUME_TEMPLATE = Template(f.read())  # noqa: E501


log = structlog.stdlib.get_logger("app.adapters.external.candidate_polling.hh")


class SwaggerModel(Protocol):
    swagger_types: dict[str, str]
    attribute_map: dict[str, str]


ResponseT = TypeVar("ResponseT", bound=SwaggerModel)


class NTDict:
    def __init__(self, data: dict):
        self.__data__ = data

    def contains(self, key: str) -> bool:
        return key in self.__data__ and self.__data__[key] is not None

    def getd(self, key: str, default: "NTDict | None" = None) -> "NTDict":
        """get inner dict"""
        if default is None:
            default = NTDict({})

        if not self.contains(key):
            return default

        return NTDict(self.__data__[key])

    def getv[T](self, key: str, default: T = None) -> T:  # type: ignore
        """get value or default"""
        if not self.contains(key):
            return default

        return self.__data__[key]

    def aget[T](self, key: str) -> T:  # type: ignore
        """assert get value"""
        return self.__data__[key]

    def dict(self) -> dict:
        return self.__data__

    def __repr__(self) -> str:
        return self.__data__.__repr__()

    def __str__(self) -> str:
        return self.__data__.__str__()


class HeadHunterCandidatePollingService:
    def __init__(
        self,
        token: str,
        user_agent: str,
        client_id: str,
        client_secret: str,
        redirect_url: str,
        user_code: str,
        access_token: str | None,
        refresh_token: str | None,
        access_token_expires_at: datetime | None,
        candidate_service: CandidateService,
        public_storage: FileStorageProtocol,
        llm_service: LLMService,
        user_service: UserService,
    ):
        self._api_client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            base_url="https://api.hh.ru",
            timeout=30.0,  # Added explicit timeout
        )
        self._application_token = token
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_url = redirect_url
        self._user_code = user_code

        self._candidate_service = candidate_service
        self._file_service = public_storage
        self._llm_service = llm_service
        self._user_service = user_service

        self.__access_token = access_token
        self.__refresh_token = refresh_token
        self.__access_token_expires_at = access_token_expires_at

        self.R = self._api_client.build_request
        self.GET = functools.partial(self.R, "GET")
        self.POST = functools.partial(self.R, "POST")
        self.PUT = functools.partial(self.R, "PUT")
        self.PATCH = functools.partial(self.R, "PATCH")
        self.DELETE = functools.partial(self.R, "DELETE")
        log.debug("HTTP method helpers created")

        log.info("HeadHunterCandidatePollingService initialized successfully")

    async def close(self) -> None:
        try:
            await self._api_client.aclose()
            log.debug("HTTP client closed successfully")
        except Exception as e:
            log.error(
                "Error closing HTTP client", error=str(e), error_type=type(e).__name__, traceback=traceback.format_exc()
            )

    async def run(self, req: httpx.Request, response_cast: type[ResponseT]) -> ResponseT:
        req_id = uuid4().hex
        method = req.method

        log.debug(
            "Performing HH API request",
            hh_req_id=req_id,
            method=method,
            url_path=req.url,
            full_url=str(req.url),
            content=req.content,
            headers={k: v for k, v in req.headers.items() if k.lower() != "authorization"},
            params=req.url.params if hasattr(req.url, "params") else None,
        )

        try:
            res = await self._api_client.send(req)

            log.debug(
                "Received HH API response",
                hh_req_id=req_id,
                status=res.status_code,
                duration_sec=res.elapsed.total_seconds(),
                headers=dict(res.headers),
                content_type=res.headers.get("content-type"),
                content_length=len(res.content),
                text_preview=res.text[:500] + ("..." if len(res.text) > 500 else ""),
            )

            res.raise_for_status()

            try:
                data = res.json()
                log.debug(
                    "Deserialized HH API response to JSON",
                    hh_req_id=req_id,
                    data_keys=list(data.keys()) if isinstance(data, dict) else None,
                    data_length=len(str(data)),
                )
            except Exception as e:
                log.error("Failed to parse JSON response", hh_req_id=req_id, error=str(e), response_text=res.text[:500])
                raise

            if not response_cast or not hasattr(response_cast, "attribute_map"):
                log.error("Invalid response_cast parameter", hh_req_id=req_id, response_cast=str(response_cast))
                raise ValueError(f"Invalid response_cast: {response_cast}")

            # Create kwargs from response data matched to model attributes
            kwargs = {}
            for key, value in response_cast.attribute_map.items():
                data_value = data.get(value) or data.get(key)
                kwargs[value] = data_value

            log.debug(
                "Casting HH API response to model",
                hh_req_id=req_id,
                response_cast=response_cast.__name__,
                attributes=response_cast.attribute_map,
                kwargs_keys=list(kwargs.keys()),
            )

            try:
                result = response_cast(**kwargs)
                log.info("Successfully cast response to model", hh_req_id=req_id, model=response_cast.__name__)
                return result
            except Exception as e:
                log.error(
                    "Failed to instantiate model from response",
                    hh_req_id=req_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    model=response_cast.__name__,
                    traceback=traceback.format_exc(),
                )
                raise

        except httpx.HTTPStatusError as e:
            log.error(
                "HTTP error in HH API request",
                hh_req_id=req_id,
                status_code=e.response.status_code,
                error=str(e),
                response_text=e.response.text[:500],
            )
            raise
        except httpx.RequestError as e:
            log.error(
                "Request error in HH API call",
                hh_req_id=req_id,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )
            raise
        except Exception as e:
            log.error(
                "Unexpected error in HH API call",
                hh_req_id=req_id,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )
            raise

    async def get_access_token(self) -> str:
        if (
            self.__access_token_expires_at is not None
            and datetime.now() < self.__access_token_expires_at
            and self.__access_token != ""
        ):  # type: ignore
            return str(self.__access_token)

        if self.__refresh_token == "":
            raise Exception("Refresh token is empty")

        token = await self.run(
            self.POST("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": self.__refresh_token}),
            hhsdk.AuthUserToken,
        )
        self.__access_token = token.access_token
        self.__refresh_token = token.refresh_token
        self.__access_token_expires_at = datetime.now() + timedelta(seconds=token.expires_in or 600)

        return str(self.__access_token)

    async def authorize(self):
        if self.__access_token is not None or self.__refresh_token is not None:
            return

        token = await self.run(
            self.POST(
                "/token",
                data={
                    "grant_type": "authorization_code",
                    "code": self._user_code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            ),
            hhsdk.AuthUserToken,
        )

        self.__access_token = str(token.access_token)
        self.__refresh_token = str(token.refresh_token)
        self.__access_token_expires_at = datetime.now() + timedelta(seconds=token.expires_in or 600)

    @span(op="candidate_polling_hh", name="get_hh_vacancy_id")
    def _get_hh_vacancy_id(self, vacancy: domain.Vacancy) -> str | None:
        if vacancy.publication.hh.state != domain.PublicationStatusEnum.PUBLISHED:
            return None

        return vacancy.publication.hh.publication_id

    @span(op="candidate_polling_hh", name="retrieve_collections_per_vacancy")
    async def _retrieve_collections_per_vacancy(
        self, hh_vacancy_id: str
    ) -> hhsdk.NegotiationsNegotiationsCollections | None:
        """
        Возвращает список откликов соискателя или список коллекций откликов/приглашений по вакансии работодателя.

        По умолчанию отклики сортируются по дате последнего обновления — от новых к старым.

        Чтобы получить список активных откликов, передайте в запросе параметр ?status=active
        """
        try:
            return await self.run(
                self.GET(
                    "/negotiations",
                    params={"status": "active", "vacancy_id": hh_vacancy_id, "order": "desc"},
                    headers={"Authorization": f"Bearer {await self.get_access_token()}"},
                ),
                hhsdk.NegotiationsNegotiationsCollections,
            )
        except Exception as e:
            log.error(
                "Failed to retrieve collections per vacancy",
                hh_vacancy_id=hh_vacancy_id,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )
            return None

    @span(op="candidate_polling_hh", name="retrieve_unprocessed_candidates")
    async def _retrieve_unprocessed_candidates(self, hh_vacancy_id: str) -> list[NTDict] | None:
        """https://api.hh.ru/negotiations/response"""
        try:
            candidates: list[NTDict] = []

            current_page = 0
            total_pages = 1

            while current_page < total_pages:  # type: ignore
                response = await self.run(
                    self.GET(
                        "/negotiations/response",
                        params={
                            "vacancy_id": hh_vacancy_id,
                            "page": current_page,
                            "order_by": "created_at",
                            "order": "desc",
                        },
                        headers={"Authorization": f"Bearer {await self.get_access_token()}"},
                    ),
                    hhsdk.NegotiationsCollectionNegotiationsResponse,
                )
                current_page += 1

                if total_pages != response.pages:
                    total_pages = response.pages

                log.debug(
                    "retrieved collections per vacancy",
                    candidates_count=len(response.items or []),
                    candidates=response.items,  # type: ignore
                )
                candidates.extend([NTDict(item) for item in response.items])  # type: ignore

            for candidate in candidates:
                action: NTDict | None = None
                raw_action: dict[str, object]
                for raw_action in candidate.getv("actions", []):
                    action_nt = NTDict(raw_action)
                    if action_nt.getv("id", "") == "consider":
                        action = action_nt
                        break

                if action is None:
                    log.warn(
                        "failed to mark candidate as considered, because action not found",
                        candidate_id=candidate.getv("id", ""),
                    )
                    continue

                url = action.getv("url", "")
                if url == "":
                    log.warn(
                        "failed to mark candidate as considered, because url not found",
                        candidate_id=candidate.getv("id", ""),
                    )
                    continue

                response = await self._api_client.send(
                    self.R(
                        action.getv("method", "PUT"),
                        url,
                        headers={"Authorization": f"Bearer {await self.get_access_token()}"},
                    )
                )
                if response.status_code != 204:
                    log.warn(
                        "failed to mark candidate as considered, because request failed",
                        candidate_id=candidate.getv("id", ""),
                        status=response.status_code,
                        response_text=response.text,
                    )

            return candidates
        except Exception as e:
            log.error(
                "Failed to retrieve candidates",
                hh_vacancy_id=hh_vacancy_id,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )
            return None

    @span(op="candidate_polling_hh", name="retrieve_full_resume")
    async def _retrieve_full_resume(self, resume_id: str) -> NTDict | None:
        try:
            response = await self._api_client.send(
                self.GET(
                    f"/resumes/{resume_id}",
                    headers={"Authorization": f"Bearer {await self.get_access_token()}"},
                ),
            )
            return NTDict(response.json())
        except Exception as e:
            log.error(
                "Failed to fetch full resume",
                resume_id=resume_id,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )
            return None

    @span(op="candidate_polling_hh", name="generate_candidate_resume")
    def _generate_candidate_resume(self, resume: NTDict) -> str:
        return CANDIDATE_RESUME_TEMPLATE.render(**resume.dict(), current_date=datetime.now().strftime("%Y-%m-%d"))

    @span(op="candidate_polling_hh", name="map_hh_to_iso_currency")
    def _map_hh_to_iso_currency(self, currency: str) -> str:
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

        return currency_mapping.get(currency, "RUB")

    @span(op="candidate_polling_hh", name="generate_create_candidate_requests")
    async def _generate_create_candidate_requests(
        self,
        vacancy: domain.Vacancy,
        candidates: list[NTDict],
    ) -> list[CandidateService.CreateCandidateRequest]:
        resulting_list: list[CandidateService.CreateCandidateRequest] = []

        for candidate in candidates:
            try:
                resume = candidate.getd("resume")
                resume_id = candidate.getd("resume").getv("id", None)
                if resume_id is None:
                    log.error("Failed to retrieve resume id", candidate=candidate)
                    continue

                full_resume = await self._retrieve_full_resume(resume_id) or NTDict({})
                log.info("retrieved full resume", resume_id=resume_id, full_resume=full_resume)
                # todo: photo_url = full_resume.get("photo", {}).get("medium", None)

                phone = None
                email = None
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
                        status=domain.VacancyStageEnum.NEW,
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

        return resulting_list

    @span(op="candidate_polling_hh", name="poll_and_analyze_new_candidates")
    async def poll_and_analyze_new_candidates(self, vacancy: domain.Vacancy) -> list[domain.Candidate]:
        """Poll HeadHunter API for new candidates for a vacancy"""
        clog = log.bind(trace_id=uuid4().hex)

        user = await self._user_service.read(UserService.ReadUserProfileRequest(id=vacancy.user_id))
        if user.tariff.analysis_used >= user.tariff.analysis_total:
            clog.info("user has reached analysis limit", user_id=vacancy.user_id)
            return []

        # https://github.com/hhru/api/blob/master/docs/employer_negotiations.md#flow

        hh_vacancy_id = self._get_hh_vacancy_id(vacancy)
        if hh_vacancy_id is None:
            clog.info("vacancy has not been published on HH", vacancy_id=vacancy.id)
            return []

        collections = await self._retrieve_collections_per_vacancy(hh_vacancy_id)
        if collections is None:
            clog.info("failed to retrieve collections per vacancy", vacancy_id=vacancy.id)
            return []

        clog.info(
            "retrieved collections per vacancy",
            vacancy_id=vacancy.id,
            collections_count=len(collections.collections),  # type: ignore
            collections=collections.collections,
        )

        candidates = await self._retrieve_unprocessed_candidates(hh_vacancy_id)
        if candidates is None:
            clog.info("failed to retrieve candidates", vacancy_id=vacancy.id)
            return []

        clog.info("retrieved candidates", candidates_count=len(candidates), candidates=candidates)

        requests = await self._generate_create_candidate_requests(vacancy, candidates)
        clog.info("generated create candidate requests", requests_count=len(requests), requests=requests)

        clog.info("creating candidates", requests_count=len(requests))
        candidates = await asyncio.gather(*[self._candidate_service.create(request) for request in requests])
        clog.info("created candidates", candidates_count=len(candidates), candidates=candidates)

        llm_requests = [
            LLMService.NewAnalyzeOperationRequest(vacancy.user_id, candidate.id, vacancy.id) for candidate in candidates
        ]

        clog.info("generating LLM tasks", llm_requests_count=len(llm_requests))
        operations = await asyncio.gather(*[
            self._llm_service.new_analyze_operation(request) for request in llm_requests
        ])
        clog.info("generated LLM tasks", llm_requests_count=len(llm_requests))

        _ = operations

        return candidates
