from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

import nanimai_platform.external_clients.hharon.hharon_api.v1 as hharon_api
from nanimai_platform.utils.map_grpc_error import AdvancedGRPCError


class HHaronSearchCampaignError(Exception): ...


class HHaronSearchCampaignValidateError(Exception): ...


class HHaronSearchCampaignGRPCError(AdvancedGRPCError): ...


class HHaronSearchCampaignProtocol(ABC):
    class CreateSearchCampaignRequest(BaseModel):
        payload: hharon_api.SearchCampaign

    class CreateSearchCampaignResponse(BaseModel):
        search_campaign_id: str

    @abstractmethod
    async def create_search_campaign(self, request: CreateSearchCampaignRequest) -> CreateSearchCampaignResponse:
        """Creates a search campaign in HHaron service.

        Args:
            request: CreateSearchCampaignRequest containing search parameters

        Raises:
            HHaronSearchCampaignValidateError - wrong data error
            HHaronSearchCampaignError - unexpected error
            HHaronSearchCampaignGRPCError - GRPC error

        Returns:
            CreateSearchCampaignResponse - search campaign id
        """
        ...
