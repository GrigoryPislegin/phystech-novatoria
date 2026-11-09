from typing import Literal, final

from pydantic import BaseModel, HttpUrl

from nanimai_platform.domain import UserID
from nanimai_platform.infra.config import HHVacancyImporterConfig
from nanimai_platform.protocols.external.vacancy_importer import (
    VacancyImporterError,
    VacancyImporterProtocol,
    WrongURLFormatError,
)


class VacancyImporterServiceError(Exception): ...


class VacancyImporterServiceWrongURLFormatError(VacancyImporterServiceError): ...


@final
class VacancyImporterService:
    def __init__(
        self,
        native_hh_vacancy_importer_adapter: VacancyImporterProtocol,
        hharon_vacancy_importer_adapter: VacancyImporterProtocol,
        hh_vacancy_importer_cfg: HHVacancyImporterConfig,
    ):
        self._hh_vacancy_importer_cfg = hh_vacancy_importer_cfg
        self._native_hh_importer_adapter = native_hh_vacancy_importer_adapter
        self._hharon_hh_importer_adapter = hharon_vacancy_importer_adapter

    def _choose_adapter(self) -> VacancyImporterProtocol:
        if self._hh_vacancy_importer_cfg.use_hharon:
            return self._hharon_hh_importer_adapter
        return self._native_hh_importer_adapter

    class ImportVacancyRequest(BaseModel):
        url: HttpUrl
        user_id: UserID
        source: Literal["hh"]

    async def import_vacancy(self, request: ImportVacancyRequest) -> VacancyImporterProtocol.ImportVacancyResponse:
        try:
            if request.source == "hh":
                adapter = self._choose_adapter()
                vacancy = await adapter.import_vacancy(
                    VacancyImporterProtocol.ImportVacancyRequest(
                        url=request.url,
                        user_id=request.user_id,
                    )
                )
            else:
                raise VacancyImporterServiceError("Only hh now is supported")
            return vacancy
        except WrongURLFormatError as e:
            raise VacancyImporterServiceWrongURLFormatError from e
        except VacancyImporterError as e:
            raise VacancyImporterServiceError from e
        except Exception as e:
            raise VacancyImporterServiceError("unknown exception") from e

    class GetVacancyIDRequest(BaseModel):
        url: HttpUrl
        source: Literal["hh"]

    class GetVacancyIDResponse(BaseModel):
        vacancy_id: str

    def get_vacancy_id(self, request: GetVacancyIDRequest) -> GetVacancyIDResponse:
        try:
            if request.source == "hh":
                adapter = self._choose_adapter()
                response = adapter.get_vacancy_id(VacancyImporterProtocol.GetVacancyIDRequest(url=request.url))
            else:
                raise VacancyImporterServiceError("only hh now is supported")

            return self.GetVacancyIDResponse(
                vacancy_id=response.vacancy_id,
            )
        except WrongURLFormatError as e:
            raise VacancyImporterServiceWrongURLFormatError("wrong url format") from e
        except VacancyImporterServiceError as e:
            raise e
        except VacancyImporterError as e:
            raise VacancyImporterServiceError("failed to get ext vacancy id") from e
        except Exception as e:
            raise VacancyImporterServiceError("unknown exception") from e
