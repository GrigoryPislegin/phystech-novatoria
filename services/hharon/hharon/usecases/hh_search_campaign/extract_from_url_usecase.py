import contextlib
from dataclasses import dataclass

from pydantic import BaseModel, HttpUrl

from hharon.pkg import hhapi
from hharon.usecases.hh_search_campaign.mapper import SearchCampaignMapperUsecase
from hharon_api.v1 import hharon_pb2


@dataclass(slots=True)
class ExtractSearchCampaignFromURL:
    mapper: SearchCampaignMapperUsecase

    class Request(BaseModel):
        url: HttpUrl

    def extract(self, request: Request) -> hharon_pb2.SearchCampaign:
        params: list[hhapi.ResumesGetParameters] = []

        for key, value in request.url.query_params():
            with contextlib.suppress(Exception):
                params.append(hhapi.ResumesGetParameters.model_validate({key: value}))

        return self.mapper.from_params(params)
