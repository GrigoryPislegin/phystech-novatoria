from dataclasses import dataclass
from typing import final, override

import structlog
from google.protobuf.timestamp_pb2 import Timestamp
from grpclib.const import Status as GRPCStatus
from grpclib.exceptions import GRPCError
from pydantic import HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from hharon import usecases
from hharon.app.server.utils import unary
from hharon.domain import SearchCampaignStatus
from hharon.pkg import mappers
from hharon.utils.grpc_error_handler import handle_grpc_errors
from hharon_api.v1 import hharon_grpc, hharon_pb2

log = structlog.stdlib.get_logger("hharon.grpc")


@final
@dataclass(slots=True)
class HharonServiceHandler(hharon_grpc.HharonServiceBase):
    # oauth
    _init_oauth_flow_usecase: usecases.InitOAuthFlow
    _complete_oauth_flow_usecase: usecases.CompleteOauthFlow[AsyncSession]
    _get_user_usecase: usecases.GetHharonUser[AsyncSession]

    # response collection
    _get_response_collection_preview_usecase: usecases.GetResponseCollectionPreviewUsecase[AsyncSession]
    _init_response_collection_usecase: usecases.InitResponseCollection[AsyncSession]
    _complete_response_collection_usecase: usecases.CompleteResponseCollection[AsyncSession]

    # search campaign
    _get_search_campaign_preview_usecase: usecases.GetSearchCampaignPreviewUsecase
    _create_search_campaign_usecase: usecases.SearchCampaignUsecase[AsyncSession]
    _init_search_campaign_execution_usecase: usecases.InitSearchCampaignExecution[AsyncSession]
    _complete_search_campaign_execution_usecase: usecases.CompleteSearchCampaignExecution[AsyncSession]
    _get_search_campaign_status_usecase: usecases.SearchCampaignUsecase[AsyncSession]
    _extract_search_campaign_usecase: usecases.ExtractSearchCampaignFromURL

    # ux
    _get_headhunter_suggestions_usecase: usecases.ProxyHeadhunterSuggestions
    _get_headhunter_vacancy_usecase: usecases.GetHeadhunterVacancyUsecase[AsyncSession]
    _get_headhunter_search_campaign_access_usecase: usecases.GetHHSearchCampaignAccessUsecase[AsyncSession]

    @override
    @handle_grpc_errors(
        (usecases.InitOAuthFlowAPIError, GRPCStatus.INTERNAL),
        (usecases.InitOAuthFlowError, GRPCStatus.INTERNAL),
    )
    @unary
    async def InitOAuthFlow(self, request: hharon_pb2.InitOAuthFlowRequest) -> hharon_pb2.InitOAuthFlowResponse:
        usecase_response = await self._init_oauth_flow_usecase.init_oauth_flow(
            usecases.InitOAuthFlow.InitOAuthFlowRequest(
                user_id=request.user_id,
                redirect_url=request.redirect_url,
            )
        )

        return hharon_pb2.InitOAuthFlowResponse(authorization_url=usecase_response.redirect_url)

    @override
    @handle_grpc_errors(
        (usecases.CompleteOauthFlowDecryptError, GRPCStatus.INVALID_ARGUMENT),
        (usecases.CompleteOauthFlowExchangeError, GRPCStatus.INTERNAL),
        (usecases.CompleteOauthFlowUserInfoError, GRPCStatus.INTERNAL),
        (usecases.CompleteOauthFlowSaveUserError, GRPCStatus.INTERNAL),
        (usecases.CompleteOauthFlowSaveTokensError, GRPCStatus.INTERNAL),
        (usecases.CompleteOauthFlowScheduleError, GRPCStatus.INTERNAL),
        (usecases.CompleteOauthFlowError, GRPCStatus.INTERNAL),
    )
    @unary
    async def CompleteOAuthFlow(
        self, request: hharon_pb2.CompleteOAuthFlowRequest
    ) -> hharon_pb2.CompleteOAuthFlowResponse:
        usecase_response = await self._complete_oauth_flow_usecase.complete_oauth_flow(
            usecases.CompleteOauthFlow.CompleteOauthFlowRequest(
                secret_code=request.secret_code,
                encrypted_state=request.encrypted_state,
                redirect_uri=request.redirect_uri,
            )
        )

        return hharon_pb2.CompleteOAuthFlowResponse(success=usecase_response.success, user_id=usecase_response.user_id)

    @override
    @handle_grpc_errors(
        (usecases.GetHharonUserNotFoundError, GRPCStatus.NOT_FOUND),
        (usecases.GetHharonUserError, GRPCStatus.INTERNAL),
    )
    @unary
    async def GetUser(self, request: hharon_pb2.GetUserRequest) -> hharon_pb2.GetUserResponse:
        usecase_response = await self._get_user_usecase.get_user(
            usecases.GetHharonUser.GetHharonUserRequest(user_id=request.user_id)
        )

        return hharon_pb2.GetUserResponse(
            user_id=usecase_response.user.user_id,
            hh_manager_id=usecase_response.user.hh_manager_id,
            hh_employer_id=usecase_response.user.hh_employer_id,
            name=usecase_response.user.name,
            email=usecase_response.user.email,
        )

    @override
    @handle_grpc_errors(
        (usecases.GetPreviewAccessDeniedError, GRPCStatus.PERMISSION_DENIED),
        (usecases.GetPreviewError, GRPCStatus.INTERNAL),
    )
    @unary
    async def GetResponseCollectionPreview(
        self, request: hharon_pb2.GetResponseCollectionPreviewRequest
    ) -> hharon_pb2.GetResponseCollectionPreviewResponse:
        usecase_response = await self._get_response_collection_preview_usecase.get_preview(
            usecases.GetResponseCollectionPreviewUsecase.GetPreviewRequest(
                hh_vacancy_id=request.hh_vacancy_id,
                user_id=request.user_id,
            )
        )

        response = hharon_pb2.GetResponseCollectionPreviewResponse(
            vacancy_title=usecase_response.vacancy_title,
            vacancy_area=usecase_response.vacancy_area,
        )
        for item in usecase_response.collections:
            response.collections.append(
                hharon_pb2.GetResponseCollectionPreviewResponse.NegotiationCollection(
                    id=item.id,
                    name=item.name,
                    total=item.total,
                    with_updates=item.with_updates,
                )
            )

        return response

    @override
    @handle_grpc_errors(
        (usecases.InitResponseCollectionError, GRPCStatus.INTERNAL),
    )
    @unary
    async def InitResponseCollection(
        self, request: hharon_pb2.InitResponseCollectionRequest
    ) -> hharon_pb2.InitResponseCollectionResponse:
        usecase_response = await self._init_response_collection_usecase.init(
            usecases.InitResponseCollection.InitResponseCollectionRequest(
                user_id=request.user_id,
                vacancy_id=request.vacancy_id,
                hh_vacancy_id=request.hh_vacancy_id,
                hh_collections=list(request.hh_collections),
            )
        )

        return hharon_pb2.InitResponseCollectionResponse(vacancy_id=usecase_response.vacancy_id)

    @override
    @handle_grpc_errors(
        (usecases.CompleteResponseCollectionNotFoundError, GRPCStatus.NOT_FOUND),
        (usecases.CompleteResponseCollectionError, GRPCStatus.INTERNAL),
    )
    @unary
    async def CompleteResponseCollection(
        self,
        request: hharon_pb2.CompleteResponseCollectionRequest,
    ) -> hharon_pb2.CompleteResponseCollectionResponse:
        usecase_response = await self._complete_response_collection_usecase.complete(
            usecases.CompleteResponseCollection.CompleteResponseCollectionRequest(
                vacancy_id=request.vacancy_id,
            )
        )

        return hharon_pb2.CompleteResponseCollectionResponse(vacancy_id=usecase_response.vacancy_id)

    @override
    @handle_grpc_errors(
        (usecases.GetSearchCampaignPreviewAccessDeniedError, GRPCStatus.PERMISSION_DENIED),
        (usecases.GetSearchCampaignPreviewRateLimitError, GRPCStatus.RESOURCE_EXHAUSTED),
        (usecases.GetSearchCampaignPreviewError, GRPCStatus.INTERNAL),
    )
    @unary
    async def GetSearchCampaignPreview(
        self,
        request: hharon_pb2.GetSearchCampaignPreviewRequest,
    ) -> hharon_pb2.GetSearchCampaignPreviewResponse:
        usecase_response = await self._get_search_campaign_preview_usecase.get_preview(
            usecases.GetSearchCampaignPreviewUsecase.GetPreviewRequest(campaign=request.campaign)
        )

        return hharon_pb2.GetSearchCampaignPreviewResponse(
            found_total_candidates=usecase_response.total_candidates,
            interval_seconds=usecase_response.interval_seconds,
            candidates_per_run=usecase_response.candidates_per_run,
        )

    @override
    @handle_grpc_errors(
        (usecases.SearchCampaignUsecaseActiveCampaignExistsError, GRPCStatus.FAILED_PRECONDITION),
        (usecases.SearchCampaignUsecaseError, GRPCStatus.INTERNAL),
    )
    @unary
    async def CreateSearchCampaign(
        self,
        request: hharon_pb2.CreateSearchCampaignRequest,
    ) -> hharon_pb2.CreateSearchCampaignResponse:
        usecase_response = await self._create_search_campaign_usecase.create(request.campaign)

        return hharon_pb2.CreateSearchCampaignResponse(vacancy_id=usecase_response.vacancy_id)

    @override
    @handle_grpc_errors(
        (usecases.InitSearchCampaignNotFoundError, GRPCStatus.NOT_FOUND),
        (usecases.InitSearchCampaignExecutionError, GRPCStatus.INTERNAL),
    )
    @unary
    async def InitSearchCampaignExecution(
        self,
        request: hharon_pb2.InitSearchCampaignExecutionRequest,
    ) -> hharon_pb2.InitSearchCampaignExecutionResponse:
        usecase_response = await self._init_search_campaign_execution_usecase.init(
            usecases.InitSearchCampaignExecution.InitSearchCampaignExecutionRequest(
                vacancy_id=request.vacancy_id,
            )
        )

        return hharon_pb2.InitSearchCampaignExecutionResponse(vacancy_id=usecase_response.vacancy_id)

    @override
    @handle_grpc_errors(
        (usecases.CompleteSearchCampaignNotFoundError, GRPCStatus.NOT_FOUND),
        (usecases.CompleteSearchCampaignExecutionError, GRPCStatus.INTERNAL),
    )
    @unary
    async def CompleteSearchCampaignExecution(
        self,
        request: hharon_pb2.CompleteSearchCampaignExecutionRequest,
    ) -> hharon_pb2.CompleteSearchCampaignExecutionResponse:
        usecase_response = await self._complete_search_campaign_execution_usecase.complete(
            usecases.CompleteSearchCampaignExecution.CompleteSearchCampaignExecutionRequest(
                vacancy_id=request.vacancy_id,
            )
        )

        return hharon_pb2.CompleteSearchCampaignExecutionResponse(vacancy_id=usecase_response.vacancy_id)

    @override
    @handle_grpc_errors((usecases.SearchCampaignUsecaseNotFoundError, GRPCStatus.NOT_FOUND))
    @unary
    async def GetSearchCampaignStatus(
        self,
        request: hharon_pb2.GetSearchCampaignStatusRequest,
    ) -> hharon_pb2.GetSearchCampaignStatusResponse:
        usecase_response = await self._get_search_campaign_status_usecase.get_search_campaign_status(
            usecases.SearchCampaignUsecase.GetSearchCampaignStatusRequest(
                vacancy_id=request.vacancy_id,
            )
        )

        mapping = {
            SearchCampaignStatus.CREATED: hharon_pb2.SEARCH_CAMPAIGN_STATUS_CREATED,
            SearchCampaignStatus.ACTIVE: hharon_pb2.SEARCH_CAMPAIGN_STATUS_ACTIVE,
            SearchCampaignStatus.COMPLETED: hharon_pb2.SEARCH_CAMPAIGN_STATUS_COMPLETED,
            SearchCampaignStatus.FAILED: hharon_pb2.SEARCH_CAMPAIGN_STATUS_FAILED,
        }

        active_until = Timestamp()
        active_until.FromDatetime(usecase_response.active_until)

        return hharon_pb2.GetSearchCampaignStatusResponse(
            status=mapping[usecase_response.status],
            vacancy_id=usecase_response.vacancy_id,
            collected_current=usecase_response.collected_current,
            collected_maximum=usecase_response.daily_maximum,
            active_until=active_until,
        )

    @override
    @handle_grpc_errors((usecases.SearchCampaignUsecaseNotFoundError, GRPCStatus.NOT_FOUND))
    @unary
    async def GetSearchCampaignSettings(
        self,
        request: hharon_pb2.GetSearchCampaignSettingsRequest,
    ) -> hharon_pb2.GetSearchCampaignSettingsResponse:
        campaign = await self._get_search_campaign_status_usecase.get_search_campaign_settings(
            usecases.SearchCampaignUsecase.GetSearchCampaignSettingsRequest(
                vacancy_id=request.vacancy_id,
            )
        )
        return hharon_pb2.GetSearchCampaignSettingsResponse(campaign=campaign)

    @override
    @unary
    async def ExtractSearchCampaign(
        self,
        request: hharon_pb2.ExtractSearchCampaignRequest,
    ) -> hharon_pb2.ExtractSearchCampaignResponse:
        response = hharon_pb2.ExtractSearchCampaignResponse()

        try:
            response.campaign.CopyFrom(
                self._extract_search_campaign_usecase.extract(
                    self._extract_search_campaign_usecase.Request(
                        url=HttpUrl(request.url),
                    )
                )
            )
        except Exception as e:
            log.exception("error extracting search campaign from url", err=e, url=request.url)

        return response

    @override
    @unary
    async def GetHeadhunterSuggestions(
        self,
        request: hharon_pb2.GetHeadhunterSuggestionsRequest,
    ) -> hharon_pb2.GetHeadhunterSuggestionsResponse:
        if request.field == hharon_pb2.GetHeadhunterSuggestionsRequest.FIELD_UNSPECIFIED:
            raise GRPCError(status=GRPCStatus.INVALID_ARGUMENT, message=f"{request.field} is not supported")

        usecase_response = await self._get_headhunter_suggestions_usecase.proxy_suggestion(
            usecases.ProxyHeadhunterSuggestions.ProxySuggestionRequest(field=request.field, text=request.text)
        )

        return hharon_pb2.GetHeadhunterSuggestionsResponse(
            suggestions=[
                hharon_pb2.GetHeadhunterSuggestionsResponse.Suggestion(
                    hh_id=suggestion.item_id,
                    text=suggestion.text,
                )
                for suggestion in usecase_response.suggestions
            ]
        )

    @override
    @handle_grpc_errors(
        (usecases.GetHeadhunterVacancyNotFoundError, GRPCStatus.NOT_FOUND),
        (usecases.GetHeadhunterVacancyAccessDeniedError, GRPCStatus.PERMISSION_DENIED),
        (usecases.GetHeadhunterVacancyError, GRPCStatus.INTERNAL),
    )
    @unary
    async def GetHeadhunterVacancy(
        self,
        request: hharon_pb2.GetHeadhunterVacancyRequest,
    ) -> hharon_pb2.GetHeadhunterVacancyResponse:
        usecase_response = await self._get_headhunter_vacancy_usecase.get_vacancy(
            usecases.GetHeadhunterVacancyUsecase.GetVacancyRequest(
                hh_vacancy_id=request.hh_vacancy_id,
                user_id=request.user_id,
            )
        )

        published_at = Timestamp()
        published_at.FromDatetime(usecase_response.published_at)

        return hharon_pb2.GetHeadhunterVacancyResponse(
            title=usecase_response.title,
            description=usecase_response.description,
            professional_roles=usecase_response.professional_roles,
            archived=usecase_response.archived,
            published_at=published_at,
            key_skills=usecase_response.key_skills,
            address_city=usecase_response.address_city,
            salary_from=usecase_response.salary_from,
            salary_to=usecase_response.salary_to,
            salary_currency=mappers.CurrencyMapper.to_proto(usecase_response.salary_currency)
            if usecase_response.salary_currency
            else None,
            salary_gross=usecase_response.salary_gross,
            employment_form=mappers.EmploymentFormMapper.to_proto(usecase_response.employment_form)
            if usecase_response.employment_form
            else None,
            work_format=[
                mappers.WorkFormatMapper.to_proto(work_format) for work_format in usecase_response.work_format
            ],
            work_schedule_by_days=[
                mappers.WorkScheduleByDaysMapper.to_proto(work_schedule)
                for work_schedule in usecase_response.work_schedule_by_days
            ],
            working_hours=[
                mappers.WorkingHoursMapper.to_proto(working_hours) for working_hours in usecase_response.working_hours
            ],
            experience=mappers.ExperienceMapper.to_proto(usecase_response.experience)
            if usecase_response.experience
            else None,
            internship=usecase_response.internship,
        )

    @override
    @unary
    async def GetHeadhunterSearchCampaignAccess(
        self,
        request: hharon_pb2.GetHeadhunterSearchCampaignAccessRequest,
    ) -> hharon_pb2.GetHeadhunterSearchCampaignAccessResponse:
        try:
            usecase_response = (
                await self._get_headhunter_search_campaign_access_usecase.get_headhunter_search_campaign_access(
                    usecases.GetHHSearchCampaignAccessUsecase.GetHHSearchCampaignAccessRequest(user_id=request.user_id)
                )
            )

            expires_at: Timestamp | None = None
            if usecase_response.expires_at:
                expires_at = Timestamp()
                expires_at.FromDatetime(usecase_response.expires_at)

            return hharon_pb2.GetHeadhunterSearchCampaignAccessResponse(
                access=usecase_response.access,
                expires_at=expires_at,
                hh_account_email=usecase_response.hh_account_email,
                hh_account_name=usecase_response.hh_account_name,
            )
        except Exception:
            return hharon_pb2.GetHeadhunterSearchCampaignAccessResponse()
