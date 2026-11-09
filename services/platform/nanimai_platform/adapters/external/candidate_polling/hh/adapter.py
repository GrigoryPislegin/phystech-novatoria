import functools
import traceback
from typing import Protocol, TypeVar, final, override
from uuid import uuid4

import hhsdk
import httpx
import structlog

from nanimai_platform.protocols.external.candidate_polling import (
    CandidatePollingProtocol as protocol,
)
from nanimai_platform.protocols.external.candidate_polling import (
    MoveToCollectionEnum,
)
from nanimai_platform.utils import NTDict

log = structlog.stdlib.get_logger("app.adapters.external.candidate_polling.hh")


class SwaggerModel(Protocol):
    swagger_types: dict[str, str]
    attribute_map: dict[str, str]


ResponseT = TypeVar("ResponseT", bound=SwaggerModel)


@final
class HHCandidatePollingAdapter(protocol):
    def __init__(self, user_agent: str) -> None:
        self.user_agent = user_agent
        self._api_client = httpx.AsyncClient(
            headers={"User-Agent": self.user_agent},
            base_url="https://api.hh.ru",
            timeout=30.0,
        )
        self.R = self._api_client.build_request
        self.GET = functools.partial(self.R, "GET")
        self.POST = functools.partial(self.R, "POST")
        # self.PUT = functools.partial(self.R, "PUT")
        # self.PATCH = functools.partial(self.R, "PATCH")
        # self.DELETE = functools.partial(self.R, "DELETE")

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

    @override
    async def retrieve_unprocessed_candidates(
        self, request: protocol.RetrieveUnprocessedCandidatesRequest
    ) -> list[NTDict] | None:
        try:
            candidates: list[NTDict] = []

            current_page = 0
            total_pages = 1

            while current_page < total_pages:  # type: ignore
                try:
                    response = await self.run(
                        self.GET(
                            "/negotiations/response",
                            params={
                                "vacancy_id": request.ext_api_vacancy_id,
                                "page": current_page,
                                "order_by": "created_at",
                                "order": "desc",
                            },
                            headers={"Authorization": f"Bearer {request.access_token}"},
                        ),
                        hhsdk.NegotiationsCollectionNegotiationsResponse,
                    )

                    if total_pages != response.pages:
                        t: int = response.pages  # pyright: ignore[reportAssignmentType] # type: ignore
                        total_pages = t

                    log.debug(
                        "retrieved collections per vacancy",
                        candidates_count=len(response.items or []),
                        candidates=response.items,  # type: ignore
                    )
                    candidates.extend([NTDict(item) for item in response.items or []])  # type: ignore
                    current_page += 1
                except Exception as e:
                    log.error(
                        "Failed to retrieve candidates",
                        hh_vacancy_id=request.ext_api_vacancy_id,
                        error=str(e),
                        error_type=type(e).__name__,
                        traceback=traceback.format_exc(),
                    )
                    current_page += 1
            return candidates
        except Exception as e:
            log.error(
                "Failed to retrieve candidates",
                hh_vacancy_id=request.ext_api_vacancy_id,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )
            return None

    @override
    async def retrieve_collections_per_vacancy(
        self, request: protocol.RetrieveCollectionsPerVacancyRequest
    ) -> NTDict | None:
        try:
            response = await self.run(
                self.GET(
                    "/negotiations",
                    params={"status": "active", "vacancy_id": request.ext_api_vacancy_id, "order": "desc"},
                    headers={"Authorization": f"Bearer {request.access_token}"},
                ),
                hhsdk.NegotiationsNegotiationsCollections,
            )
            return NTDict(response.collections or {})
        except Exception as e:
            log.error(
                "Failed to retrieve collections",
                hh_vacancy_id=request.ext_api_vacancy_id,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )
            return None

    @override
    async def retrieve_full_resume(self, request: protocol.RetrieveFullResumeRequest) -> NTDict | None:
        try:
            response = await self._api_client.send(
                self.GET(
                    f"/resumes/{request.resume_id}",
                    headers={"Authorization": f"Bearer {request.access_token}"},
                ),
            )
            return NTDict(response.json())
        except Exception as e:
            log.error(
                "Failed to fetch full resume",
                resume_id=request.resume_id,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )
            return None

    @override
    async def move_candidate_to_collection(
        self, item: NTDict, move_to: MoveToCollectionEnum, access_token: str
    ) -> None:
        action = None
        for act in item.getv("actions", []):
            act = NTDict(act)
            if act.getv("id", "") == move_to:
                action = act
                break

        if action is None:
            log.warn(
                "failed to mark candidate as considered, because action not found",
                candidate_id=item.getv("id", ""),
            )
            return

        url = action.getv("url", "")
        if url == "":
            log.warn(
                "failed to mark candidate as considered, because url not found",
                candidate_id=item.getv("id", ""),
            )
            return

        response = await self._api_client.send(
            self.R(
                action.getv("method", "PUT"),
                url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        )
        if response.status_code != 204:
            log.warn(
                "failed to mark candidate as considered, because request failed",
                candidate_id=item.getv("id", ""),
                status=response.status_code,
                response_text=response.text,
            )
