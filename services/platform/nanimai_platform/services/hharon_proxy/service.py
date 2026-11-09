from typing import Protocol, final

from grpclib.const import Status as GRPCStatus
from grpclib.exceptions import GRPCError

import nanimai_platform.external_clients.hharon.hharon_api.v1 as hharon_api
from nanimai_platform.domain import UserID, VacancyID


class HHaronClient(Protocol):
    async def init_o_auth_flow(
        self,
        message: "hharon_api.InitOAuthFlowRequest",
    ) -> "hharon_api.InitOAuthFlowResponse": ...
    async def complete_o_auth_flow(
        self,
        message: "hharon_api.CompleteOAuthFlowRequest",
    ) -> "hharon_api.CompleteOAuthFlowResponse": ...
    async def get_user(
        self,
        message: "hharon_api.GetUserRequest",
    ) -> "hharon_api.GetUserResponse": ...
    async def get_response_collection_preview(
        self,
        message: "hharon_api.GetResponseCollectionPreviewRequest",
    ) -> "hharon_api.GetResponseCollectionPreviewResponse": ...
    async def init_response_collection(
        self,
        message: "hharon_api.InitResponseCollectionRequest",
    ) -> "hharon_api.InitResponseCollectionResponse": ...
    async def complete_response_collection(
        self,
        message: "hharon_api.CompleteResponseCollectionRequest",
    ) -> "hharon_api.CompleteResponseCollectionResponse": ...
    async def get_search_campaign_preview(
        self,
        message: "hharon_api.GetSearchCampaignPreviewRequest",
    ) -> "hharon_api.GetSearchCampaignPreviewResponse": ...
    async def create_search_campaign(
        self,
        message: "hharon_api.CreateSearchCampaignRequest",
    ) -> "hharon_api.CreateSearchCampaignResponse": ...
    async def init_search_campaign_execution(
        self,
        message: "hharon_api.InitSearchCampaignExecutionRequest",
    ) -> "hharon_api.InitSearchCampaignExecutionResponse": ...
    async def complete_search_campaign_execution(
        self,
        message: "hharon_api.CompleteSearchCampaignExecutionRequest",
    ) -> "hharon_api.CompleteSearchCampaignExecutionResponse": ...
    async def get_search_campaign_status(
        self,
        message: "hharon_api.GetSearchCampaignStatusRequest",
    ) -> "hharon_api.GetSearchCampaignStatusResponse": ...
    async def get_search_campaign_settings(
        self,
        message: "hharon_api.GetSearchCampaignSettingsRequest",
    ) -> "hharon_api.GetSearchCampaignSettingsResponse": ...
    async def get_headhunter_suggestions(
        self,
        message: "hharon_api.GetHeadhunterSuggestionsRequest",
    ) -> "hharon_api.GetHeadhunterSuggestionsResponse": ...
    async def get_headhunter_vacancy(
        self,
        message: "hharon_api.GetHeadhunterVacancyRequest",
    ) -> "hharon_api.GetHeadhunterVacancyResponse": ...
    async def get_headhunter_search_campaign_access(
        self,
        message: "hharon_api.GetHeadhunterSearchCampaignAccessRequest",
    ) -> "hharon_api.GetHeadhunterSearchCampaignAccessResponse": ...

    async def extract_search_campaign(
        self,
        message: "hharon_api.ExtractSearchCampaignRequest",
    ) -> "hharon_api.ExtractSearchCampaignResponse": ...


class HharonError(Exception): ...


class HharonInvalidArgumentError(HharonError): ...


class HharonNotFoundError(HharonError): ...


@final
class HHaronProxyService:
    def __init__(self, client: HHaronClient):
        self.client = client

    async def get_headhunter_suggestions(
        self, field: hharon_api.GetHeadhunterSuggestionsRequestField, text: str
    ) -> hharon_api.GetHeadhunterSuggestionsResponse:
        if field == hharon_api.GetHeadhunterSuggestionsRequestField.UNSPECIFIED:
            raise HharonInvalidArgumentError("invalid field")

        response = await self.client.get_headhunter_suggestions(
            hharon_api.GetHeadhunterSuggestionsRequest(field=field, text=text)
        )

        return response

    async def get_search_campaign_status(self, vacancy_id: VacancyID) -> hharon_api.GetSearchCampaignStatusResponse:
        response = await self.client.get_search_campaign_status(
            hharon_api.GetSearchCampaignStatusRequest(vacancy_id=str(vacancy_id))
        )
        return response

    async def get_search_campaign_settings(self, vacancy_id: VacancyID) -> hharon_api.GetSearchCampaignSettingsResponse:
        try:
            response = await self.client.get_search_campaign_settings(
                hharon_api.GetSearchCampaignSettingsRequest(vacancy_id=str(vacancy_id))
            )
            return response
        except GRPCError as e:
            if e.status == GRPCStatus.NOT_FOUND:
                raise HharonNotFoundError("search campaign not found") from e
            raise HharonError("hharon error") from e

    async def complete_search_campaign_execution(
        self, vacancy_id: VacancyID
    ) -> hharon_api.CompleteSearchCampaignExecutionResponse:
        response = await self.client.complete_search_campaign_execution(
            hharon_api.CompleteSearchCampaignExecutionRequest(vacancy_id=str(vacancy_id))
        )
        return response

    async def complete_response_collection(
        self, vacancy_id: VacancyID
    ) -> hharon_api.CompleteResponseCollectionResponse:
        response = await self.client.complete_response_collection(
            hharon_api.CompleteResponseCollectionRequest(vacancy_id=str(vacancy_id))
        )
        return response

    async def get_headhunter_search_campaign_access(
        self, user_id: UserID
    ) -> hharon_api.GetHeadhunterSearchCampaignAccessResponse:
        response = await self.client.get_headhunter_search_campaign_access(
            hharon_api.GetHeadhunterSearchCampaignAccessRequest(user_id=str(user_id))
        )
        return response

    async def get_headhunter_vacancy(
        self, user_id: UserID, hh_vacancy_id: str
    ) -> hharon_api.GetHeadhunterVacancyResponse:
        response = await self.client.get_headhunter_vacancy(
            hharon_api.GetHeadhunterVacancyRequest(hh_vacancy_id=hh_vacancy_id, user_id=str(user_id))
        )
        return response

    async def create_search_campaign(
        self, campaign: hharon_api.SearchCampaign
    ) -> hharon_api.CreateSearchCampaignResponse:
        response = await self.client.create_search_campaign(hharon_api.CreateSearchCampaignRequest(campaign=campaign))
        return response

    async def init_search_campaign(
        self, request: hharon_api.InitSearchCampaignExecutionRequest
    ) -> hharon_api.InitSearchCampaignExecutionResponse:
        response = await self.client.init_search_campaign_execution(request)
        return response

    async def get_user(self, user_id: UserID) -> hharon_api.GetUserResponse:
        try:
            return await self.client.get_user(hharon_api.GetUserRequest(user_id=str(user_id)))
        except Exception as e:
            raise HharonError("no user exist in hharon") from e

    async def extract_from_url(self, url: str) -> hharon_api.ExtractSearchCampaignResponse:
        return await self.client.extract_search_campaign(hharon_api.ExtractSearchCampaignRequest(url=url))

    async def get_response_collection_preview(
        self, user_id: UserID, hh_vacancy_id: str
    ) -> hharon_api.GetResponseCollectionPreviewResponse:
        return await self.client.get_response_collection_preview(
            hharon_api.GetResponseCollectionPreviewRequest(user_id=str(user_id), hh_vacancy_id=hh_vacancy_id)
        )

    async def init_response_collection(
        self, user_id: UserID, vacancy_id: VacancyID, hh_vacancy_id: str, hh_collections: list[str]
    ) -> hharon_api.InitResponseCollectionResponse:
        return await self.client.init_response_collection(
            hharon_api.InitResponseCollectionRequest(
                user_id=str(user_id),
                vacancy_id=str(vacancy_id),
                hh_vacancy_id=hh_vacancy_id,
                hh_collections=hh_collections,
            )
        )

    async def get_search_campaign_preview(
        self, user_id: UserID, campaign: hharon_api.SearchCampaign
    ) -> hharon_api.GetSearchCampaignPreviewResponse:
        campaign.user_id = str(user_id)
        return await self.client.get_search_campaign_preview(
            hharon_api.GetSearchCampaignPreviewRequest(campaign=campaign)
        )
