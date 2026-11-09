from collections.abc import AsyncGenerator
from typing import final, override

import httpx
import structlog

import hharon.protocols.response_collection.hh_protocol as protocol
from hharon.infra.headhunter import HHHTTPError, HeadHunterClient, handle_hh_http_error
from hharon.pkg import hhapi

log = structlog.stdlib.get_logger("hharon.adapters.HeadHunterResponseCollectionAdapter")


@final
class HeadHunterResponseCollectionAdapter(
    protocol.ResponseCollectionHHApiProtocol, protocol.ResponseCollectionPreviewHHApiProtocol
):
    """Adapter for HeadHunter API to collect responses from collections."""

    def __init__(self, client: HeadHunterClient) -> None:
        self._client = client

    @override
    async def get_responses_from_collection(
        self, collection_id: str, vacancy_id: str, access_token: str
    ) -> AsyncGenerator[hhapi.Item2]:
        """Get responses from a collection as async generator.

        Args:
            collection_id: ID of the collection
            vacancy_id: ID of the vacancy
            access_token: HeadHunter API access token

        Yields:
            Item2: Response items from the collection

        Raises:
            HeadHunterRateLimitError: On rate limit (429)
            HeadHunterAccessDeniedError: On access denied (403)
            HeadHunterResponseCollectionError: On other errors
        """
        page = 0
        per_page = 20  # Standard HH API page size

        while True:
            try:
                response = await self._client.get(
                    f"/negotiations/{collection_id}",
                    response_model=hhapi.NegotiationsCollectionNegotiationsResponse,
                    params=hhapi.NegotiationsResponseGetParameters(
                        vacancy_id=vacancy_id,
                        page=page,
                        per_page=per_page,
                        order_by=hhapi.NegotiationsOrderEnum.CREATED_AT,
                    ),
                    headers={"Authorization": f"Bearer {access_token}"},
                )

                if not response.items:
                    break

                for item in response.items:
                    yield item

                if page >= response.pages - 1:
                    break

                page += 1

            except HHHTTPError as e:
                handle_hh_http_error(
                    e,
                    operation="getting responses from collection",
                    forbid_403_msg="Access denied to collection",
                    forbid_404_msg="Collection not found or no access",
                    rate_limit_error_cls=protocol.HeadHunterRateLimitError,
                    access_denied_error_cls=protocol.HeadHunterAccessDeniedError,
                    generic_error_cls=protocol.HeadHunterResponseCollectionError,
                    collection_id=collection_id,
                )
            except Exception as e:
                log.exception("unexpected error getting responses", collection_id=collection_id)
                raise protocol.HeadHunterResponseCollectionError("Unexpected error") from e

    @override
    async def get_resume(self, resume_id: str, access_token: str) -> hhapi.ResumeResumeForEmployer:
        """Get full resume by ID.

        Args:
            resume_id: ID of the resume
            access_token: HeadHunter API access token

        Returns:
            ResumeResumeForEmployer: Full resume data

        Raises:
            HeadHunterRateLimitError: On rate limit (429)
            HeadHunterAccessDeniedError: On access denied (403/404)
            HeadHunterResponseCollectionError: On other errors
        """
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
                forbid_404_msg="Access denied to resume",
                rate_limit_error_cls=protocol.HeadHunterRateLimitError,
                access_denied_error_cls=protocol.HeadHunterAccessDeniedError,
                generic_error_cls=protocol.HeadHunterResponseCollectionError,
                resume_id=resume_id,
            )
        except Exception as e:
            log.exception("unexpected error getting resume", resume_id=resume_id)
            raise protocol.HeadHunterResponseCollectionError("Unexpected error") from e

    @override
    async def get_negotiations(
        self, access_token: str, hh_vacancy_id: str
    ) -> hhapi.NegotiationsNegotiationsCollections:
        try:
            return await self._client.get(
                "/negotiations",
                response_model=hhapi.NegotiationsNegotiationsCollections,
                headers={"Authorization": f"Bearer {access_token}"},
                params=hhapi.NegotiationsGetParameters(vacancy_id=hh_vacancy_id),
            )
        except HHHTTPError as e:
            if e.status_code == httpx.codes.NOT_FOUND.value:
                raise protocol.ResponseCollectionPreviewHHApiNotFoundError from e

            if e.status_code == httpx.codes.FORBIDDEN.value:
                raise protocol.ResponseCollectionPreviewHHApiAccessDeniedError from e

            raise protocol.ResponseCollectionPreviewHHApiError from e
        except Exception as e:
            log.exception("unexpected error getting negotiations")
            raise protocol.ResponseCollectionPreviewHHApiError("Unexpected error") from e

    @override
    async def get_vacancies_vacancy_id(
        self, access_token: str, hh_vacancy_id: str
    ) -> hhapi.VacanciesVacancyForManager | hhapi.VacanciesVacancyForApplicant:
        try:
            vacancy = await self._client.get(
                f"/vacancies/{hh_vacancy_id}",
                response_model=hhapi.VacanciesVacancy,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except HHHTTPError as e:
            if e.status_code == httpx.codes.FORBIDDEN.value:
                raise protocol.ResponseCollectionPreviewHHApiAccessDeniedError from e

            if e.status_code == httpx.codes.NOT_FOUND.value:
                raise protocol.ResponseCollectionPreviewHHApiNotFoundError from e

            raise protocol.ResponseCollectionPreviewHHApiError from e
        except Exception as e:
            log.exception("unexpected error getting vacancy")
            raise protocol.ResponseCollectionPreviewHHApiError("Unexpected error") from e
        else:
            return vacancy.root
