from collections.abc import AsyncGenerator
from typing import final, override

import structlog

from hharon.infra.headhunter import HHHTTPError, HeadHunterClient, handle_hh_http_error, handle_resume_search_http_error
from hharon.pkg import hhapi
from hharon.protocols.resume_search_scan import protocol

log = structlog.stdlib.get_logger("hharon.adapters.HeadHunterResumeSearchScanAdapter")


@final
class HeadHunterResumeSearchScanAdapter(protocol.ResumeSearchScanHHApiProtocol):
    """Adapter for HeadHunter API: поиск резюме по фильтрам."""

    def __init__(self, client: HeadHunterClient) -> None:
        self._client = client

    @override
    async def get_resumes_from_search(
        self, access_token: str, params: list[hhapi.ResumesGetParameters]
    ) -> AsyncGenerator[hhapi.ResumesSearchForResumesItem]:
        page = 0

        while True:
            try:
                response = await self._client.get(
                    "/resumes",
                    response_model=hhapi.ResumesSearchForResumesResponse,
                    params=[*params, hhapi.ResumesGetParameters(page=page, per_page=20)],
                    headers={"Authorization": f"Bearer {access_token}"},
                )

                log.info(
                    "completed search campaign request",
                    items_count=len(response.items),
                    page=page,
                    total_pages=response.pages,
                )

                if not response.items:
                    break

                for item in response.items:
                    yield item

                if page >= response.pages - 1:
                    break

                page += 1

            except HHHTTPError as e:
                handle_resume_search_http_error(e, "getting resumes from search")
            except Exception as e:
                log.exception("unexpected error getting resumes from search")
                raise protocol.HeadHunterResumeSearchScanError("Unexpected error") from e

    @override
    async def get_resume_search_count(self, access_token: str, params: list[hhapi.ResumesGetParameters]) -> int:
        try:
            response = await self._client.get(
                "/resumes",
                response_model=hhapi.ResumesSearchForResumesResponse,
                params=[*params, hhapi.ResumesGetParameters(page=0, per_page=1)],
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except HHHTTPError as e:
            handle_resume_search_http_error(e, "getting resume search count")
        except Exception as e:
            log.exception("unexpected error getting resume search count")
            raise protocol.HeadHunterResumeSearchScanError("Unexpected error") from e
        else:
            return response.found

    @override
    async def get_resume(self, resume_id: str, access_token: str) -> hhapi.ResumeResumeForEmployer:
        """Get full resume by ID (delegate to same client as response collection)."""
        try:
            return await self._client.get(
                f"/resumes/{resume_id}",
                response_model=hhapi.ResumeResumeForEmployer,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except HHHTTPError as e:
            handle_hh_http_error(
                e,
                operation="getting resume",
                forbid_403_msg="Access denied to resume",
                forbid_404_msg=None,
                rate_limit_error_cls=protocol.HeadHunterRateLimitError,
                access_denied_error_cls=protocol.HeadHunterAccessDeniedError,
                generic_error_cls=protocol.HeadHunterResumeSearchScanError,
                resume_id=resume_id,
            )
        except Exception as e:
            log.exception("unexpected error getting resume", resume_id=resume_id)
            raise protocol.HeadHunterResumeSearchScanError("Unexpected error") from e
