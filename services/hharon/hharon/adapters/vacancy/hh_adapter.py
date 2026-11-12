from __future__ import annotations

from typing import final, override

import httpx
import structlog

from hharon.infra.headhunter import HHHTTPError, HeadHunterClient
from hharon.pkg import hhapi
from hharon.protocols import vacancy as vacancy_protocol

log = structlog.stdlib.get_logger("hharon.adapters.HHVacancyImportAdapter")


@final
class HHGetVacancyAdapter(vacancy_protocol.GetVacancyByIDProtocol):
    def __init__(self, *, client: HeadHunterClient) -> None:
        self._client = client

    async def _fetch(
        self, vacancy_id: str, *, headers: dict[str, str]
    ) -> hhapi.VacanciesVacancyForApplicant | hhapi.VacanciesVacancyForManager:
        vacancy = await self._client.get(
            f"/vacancies/{vacancy_id}",
            response_model=hhapi.VacanciesVacancy,
            headers=headers,
        )
        return vacancy.root

    @override
    async def get_vacancy_by_id(
        self, request: vacancy_protocol.GetVacancyByIDProtocol.GetVacancyByIDRequest
    ) -> hhapi.VacanciesVacancyForApplicant | hhapi.VacanciesVacancyForManager:
        try:
            headers = {"Authorization": f"Bearer {request.access_token}"} if request.access_token else {}
            return await self._fetch(request.vacancy_id, headers=headers)
        except HHHTTPError as e:
            if e.status_code == httpx.codes.FORBIDDEN.value:
                raise vacancy_protocol.GetVacancyByIDAccessDeniedError("Private vacancy, access denied") from e
            raise vacancy_protocol.GetVacancyByIDError("Failed to fetch vacancy from HH API") from e
        except vacancy_protocol.GetVacancyByIDError:
            raise
        except Exception as e:
            log.exception("Failed to fetch vacancy from HH API", vacancy_id=request.vacancy_id)
            raise vacancy_protocol.GetVacancyByIDError("Failed to fetch vacancy from HH API") from e
