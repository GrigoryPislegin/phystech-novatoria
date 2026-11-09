from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import grpclib.exceptions
import pytest
from grpclib.const import Status as GRPCStatus

from hharon.usecases.response_collection.complete_usecase import CompleteResponseCollection
from hharon.usecases.response_collection.init_usecase import InitResponseCollection
from hharon.usecases.resume_search_scan.complete_usecase import CompleteSearchCampaignExecution
from hharon.usecases.resume_search_scan.get_preview_usecase import (
    GetSearchCampaignPreviewAccessDeniedError,
    GetSearchCampaignPreviewError,
    GetSearchCampaignPreviewRateLimitError,
    GetSearchCampaignPreviewUsecase,
)
from hharon.usecases.resume_search_scan.init_usecase import InitSearchCampaignExecution
from hharon.usecases.vacancy.get_vacancy_usecase import GetHeadhunterVacancyUsecase

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from hharon.app.server.grpc_handler import HharonServiceHandler
from hharon.domain.scalars import HharonUserID, SearchCampaignID
from hharon.domain.search_campaign import SearchCampaignStatus
from hharon.domain.user import HharonUser
from hharon.usecases import ProxyHeadhunterSuggestions
from hharon.usecases.hh_manager_access import GetHHSearchCampaignAccessUsecase
from hharon.usecases.hh_search_campaign import (
    ExtractSearchCampaignFromURL,
    SearchCampaignUsecase,
    SearchCampaignUsecaseError,
    SearchCampaignUsecaseNotFoundError,
)
from hharon.usecases.hh_search_campaign.usecase import SearchCampaignUsecase as SearchCampaignUsecaseImpl
from hharon.usecases.oauth2 import CompleteOauthFlow, InitOAuthFlow
from hharon.usecases.response_collection import GetResponseCollectionPreviewUsecase
from hharon.usecases.user import GetHharonUser, GetHharonUserError, GetHharonUserNotFoundError
from hharon_api.v1 import hharon_pb2


@pytest.fixture
def grpc_handler(
    init_oauth_flow_usecase: Mock,
    complete_oauth_flow_usecase: Mock,
    get_user_usecase: Mock,
    init_response_collection_usecase: Mock,
    complete_response_collection_usecase: Mock,
    init_search_campaign_execution_usecase: Mock,
    get_response_collection_preview_usecase: Mock,
    get_search_campaign_preview_usecase: Mock,
    get_vacancy_usecase: Mock,
    get_manager_access_usecase: Mock,
    hh_search_campaign_usecase: Mock,
    proxy_headhunter_suggestions_usecase: Mock,
    complete_search_campaign_execution_usecase: Mock,
    extract_search_campaign_usecase: Mock,
) -> HharonServiceHandler:
    """Fixture to create HharonServiceHandler."""
    return HharonServiceHandler(
        _init_oauth_flow_usecase=cast("InitOAuthFlow", init_oauth_flow_usecase),
        _complete_oauth_flow_usecase=cast("CompleteOauthFlow[AsyncSession]", complete_oauth_flow_usecase),
        _get_user_usecase=cast("GetHharonUser[AsyncSession]", get_user_usecase),
        _get_response_collection_preview_usecase=cast(
            "GetResponseCollectionPreviewUsecase[AsyncSession]", get_response_collection_preview_usecase
        ),
        _init_response_collection_usecase=cast(
            "InitResponseCollection[AsyncSession]", init_response_collection_usecase
        ),
        _complete_response_collection_usecase=cast(
            "CompleteResponseCollection[AsyncSession]", complete_response_collection_usecase
        ),
        _get_search_campaign_preview_usecase=cast(
            "GetSearchCampaignPreviewUsecase", get_search_campaign_preview_usecase
        ),
        _create_search_campaign_usecase=cast("SearchCampaignUsecase[AsyncSession]", hh_search_campaign_usecase),
        _init_search_campaign_execution_usecase=cast(
            "InitSearchCampaignExecution[AsyncSession]",
            init_search_campaign_execution_usecase,
        ),
        _complete_search_campaign_execution_usecase=cast(
            "CompleteSearchCampaignExecution[AsyncSession]",
            complete_search_campaign_execution_usecase,
        ),
        _get_search_campaign_status_usecase=cast("SearchCampaignUsecase[AsyncSession]", hh_search_campaign_usecase),
        _get_headhunter_suggestions_usecase=cast("ProxyHeadhunterSuggestions", proxy_headhunter_suggestions_usecase),
        _get_headhunter_vacancy_usecase=cast("GetHeadhunterVacancyUsecase[AsyncSession]", get_vacancy_usecase),
        _get_headhunter_search_campaign_access_usecase=cast(
            "GetHHSearchCampaignAccessUsecase[AsyncSession]", get_manager_access_usecase
        ),
        _extract_search_campaign_usecase=cast("ExtractSearchCampaignFromURL", extract_search_campaign_usecase),
    )


@pytest.mark.asyncio
async def test_get_user_returns_user_successfully(
    grpc_handler: HharonServiceHandler,
    get_user_usecase: Mock,
    mock_stream: Mock,
    get_user_request: "hharon_pb2.GetUserRequest",
) -> None:
    """Test that GetUser returns user successfully."""
    hharon_id = HharonUserID()
    user = HharonUser(
        hharon_id=hharon_id,
        user_id="user_123",
        hh_manager_id="hh_123",
        hh_employer_id="employer_123",
        name="John Doe",
        email="john@example.com",
    )

    mock_stream.recv_message.return_value = get_user_request  # pyright: ignore[reportAny]

    usecase_response = GetHharonUser.GetHharonUserResponse(user=user)
    get_user_usecase.get_user = AsyncMock(return_value=usecase_response)

    await grpc_handler.GetUser(mock_stream)

    # Verify usecase was called correctly
    get_user_usecase.get_user.assert_awaited_once()  # pyright: ignore[reportAny]
    call_args = get_user_usecase.get_user.await_args[0][0]  # pyright: ignore[reportAny]
    assert call_args.user_id == "some_id"  # pyright: ignore[reportAny]

    # Verify response was sent
    mock_stream.send_message.assert_awaited_once()  # pyright: ignore[reportAny]
    sent_response = mock_stream.send_message.await_args[0][0]  # pyright: ignore[reportAny]
    assert isinstance(sent_response, hharon_pb2.GetUserResponse)
    assert sent_response.user_id == "user_123"
    assert sent_response.hh_manager_id == "hh_123"
    assert sent_response.name == "John Doe"
    assert sent_response.email == "john@example.com"
    assert sent_response.hh_employer_id == "employer_123"


@pytest.mark.asyncio
async def test_get_user_handles_none_request(grpc_handler: HharonServiceHandler, mock_stream: Mock) -> None:
    """Test that GetUser handles None request gracefully."""
    mock_stream.recv_message.return_value = None  # pyright: ignore[reportAny]

    await grpc_handler.GetUser(mock_stream)

    # Should return early without calling usecase
    mock_stream.send_message.assert_not_awaited()  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_get_user_raises_not_found_error(
    grpc_handler: HharonServiceHandler,
    get_user_usecase: Mock,
    mock_stream: Mock,
    get_user_request: "hharon_pb2.GetUserRequest",
) -> None:
    """Test that GetUser raises NOT_FOUND error when user is not found."""
    mock_stream.recv_message.return_value = get_user_request  # pyright: ignore[reportAny]

    get_user_usecase.get_user = AsyncMock(side_effect=GetHharonUserNotFoundError("User not found"))

    with pytest.raises(grpclib.exceptions.GRPCError) as exc_info:
        await grpc_handler.GetUser(mock_stream)

    assert exc_info.value.status == GRPCStatus.NOT_FOUND
    get_user_usecase.get_user.assert_awaited_once()  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_get_user_raises_internal_error(
    grpc_handler: HharonServiceHandler,
    get_user_usecase: Mock,
    mock_stream: Mock,
    get_user_request: "hharon_pb2.GetUserRequest",
) -> None:
    """Test that GetUser raises INTERNAL error on GetHharonUserError."""
    mock_stream.recv_message.return_value = get_user_request  # pyright: ignore[reportAny]

    get_user_usecase.get_user = AsyncMock(side_effect=GetHharonUserError("Internal error"))

    with pytest.raises(grpclib.exceptions.GRPCError) as exc_info:
        await grpc_handler.GetUser(mock_stream)

    assert exc_info.value.status == GRPCStatus.INTERNAL
    get_user_usecase.get_user.assert_awaited_once()  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_get_user_raises_internal_error_on_unexpected_exception(
    grpc_handler: HharonServiceHandler,
    get_user_usecase: Mock,
    mock_stream: Mock,
    get_user_request: "hharon_pb2.GetUserRequest",
) -> None:
    """Test that GetUser raises INTERNAL error on unexpected exception."""
    mock_stream.recv_message.return_value = get_user_request  # pyright: ignore[reportAny]

    get_user_usecase.get_user = AsyncMock(side_effect=ValueError("Unexpected error"))

    with pytest.raises(grpclib.exceptions.GRPCError) as exc_info:
        await grpc_handler.GetUser(mock_stream)

    assert exc_info.value.status == GRPCStatus.INTERNAL
    get_user_usecase.get_user.assert_awaited_once()  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_get_search_campaign_preview_returns_response_successfully(
    grpc_handler: HharonServiceHandler,
    get_search_campaign_preview_usecase: Mock,
    mock_stream: Mock,
) -> None:
    """Test that GetSearchCampaignPreview returns response successfully."""

    campaign = hharon_pb2.SearchCampaign(
        user_id="user_123",
        vacancy_id="vacancy_123",
        daily_limit=30,
    )
    campaign.active_until.GetCurrentTime()
    request = hharon_pb2.GetSearchCampaignPreviewRequest(campaign=campaign)

    mock_stream.recv_message.return_value = request  # pyright: ignore[reportAny]

    usecase_response = GetSearchCampaignPreviewUsecase.GetPreviewResponse(
        total_candidates=150,
        interval_seconds=28800,
        candidates_per_run=10,
    )
    get_search_campaign_preview_usecase.get_preview = AsyncMock(return_value=usecase_response)

    await grpc_handler.GetSearchCampaignPreview(mock_stream)

    get_search_campaign_preview_usecase.get_preview.assert_awaited_once()  # pyright: ignore[reportAny]
    call_args = get_search_campaign_preview_usecase.get_preview.await_args[0][0]  # pyright: ignore[reportAny]
    assert call_args.campaign == campaign

    mock_stream.send_message.assert_awaited_once()  # pyright: ignore[reportAny]
    sent_response = mock_stream.send_message.await_args[0][0]  # pyright: ignore[reportAny]
    assert isinstance(sent_response, hharon_pb2.GetSearchCampaignPreviewResponse)
    assert sent_response.found_total_candidates == 150
    assert sent_response.interval_seconds == 28800
    assert sent_response.candidates_per_run == 10


@pytest.mark.asyncio
async def test_get_search_campaign_preview_raises_permission_denied(
    grpc_handler: HharonServiceHandler,
    get_search_campaign_preview_usecase: Mock,
    mock_stream: Mock,
) -> None:
    """Test that GetSearchCampaignPreview raises PERMISSION_DENIED on access denied."""

    campaign = hharon_pb2.SearchCampaign(user_id="user_123", vacancy_id="vacancy_123", daily_limit=30)
    campaign.active_until.GetCurrentTime()
    request = hharon_pb2.GetSearchCampaignPreviewRequest(campaign=campaign)

    mock_stream.recv_message.return_value = request  # pyright: ignore[reportAny]
    get_search_campaign_preview_usecase.get_preview = AsyncMock(
        side_effect=GetSearchCampaignPreviewAccessDeniedError("access denied")
    )

    with pytest.raises(grpclib.exceptions.GRPCError) as exc_info:
        await grpc_handler.GetSearchCampaignPreview(mock_stream)

    assert exc_info.value.status == GRPCStatus.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_get_search_campaign_preview_raises_internal_error(
    grpc_handler: HharonServiceHandler,
    get_search_campaign_preview_usecase: Mock,
    mock_stream: Mock,
) -> None:
    """Test that GetSearchCampaignPreview raises INTERNAL on GetSearchCampaignPreviewError."""

    campaign = hharon_pb2.SearchCampaign(user_id="user_123", vacancy_id="vacancy_123", daily_limit=30)
    campaign.active_until.GetCurrentTime()
    request = hharon_pb2.GetSearchCampaignPreviewRequest(campaign=campaign)

    mock_stream.recv_message.return_value = request  # pyright: ignore[reportAny]
    get_search_campaign_preview_usecase.get_preview = AsyncMock(
        side_effect=GetSearchCampaignPreviewError("internal error")
    )

    with pytest.raises(grpclib.exceptions.GRPCError) as exc_info:
        await grpc_handler.GetSearchCampaignPreview(mock_stream)

    assert exc_info.value.status == GRPCStatus.INTERNAL


@pytest.mark.asyncio
async def test_get_search_campaign_preview_raises_resource_exhausted_on_rate_limit(
    grpc_handler: HharonServiceHandler,
    get_search_campaign_preview_usecase: Mock,
    mock_stream: Mock,
) -> None:
    """Test that GetSearchCampaignPreview raises RESOURCE_EXHAUSTED on HH rate limit (429)."""
    campaign = hharon_pb2.SearchCampaign(user_id="user_123", vacancy_id="vacancy_123", daily_limit=30)
    campaign.active_until.GetCurrentTime()
    request = hharon_pb2.GetSearchCampaignPreviewRequest(campaign=campaign)

    mock_stream.recv_message.return_value = request  # pyright: ignore[reportAny]
    get_search_campaign_preview_usecase.get_preview = AsyncMock(
        side_effect=GetSearchCampaignPreviewRateLimitError("Rate limit exceeded", retry_after=60)
    )

    with pytest.raises(grpclib.exceptions.GRPCError) as exc_info:
        await grpc_handler.GetSearchCampaignPreview(mock_stream)

    assert exc_info.value.status == GRPCStatus.RESOURCE_EXHAUSTED


@pytest.mark.asyncio
async def test_get_search_campaign_status_returns_status_successfully(
    grpc_handler: HharonServiceHandler,
    hh_search_campaign_usecase: Mock,
    mock_stream: Mock,
) -> None:
    """Test that GetSearchCampaignStatus returns status successfully when SearchCampaign exists."""
    vacancy_id = "vacancy_123"
    campaign_id = uuid4()

    request = hharon_pb2.GetSearchCampaignStatusRequest(
        vacancy_id=vacancy_id,
    )

    mock_stream.recv_message.return_value = request  # pyright: ignore[reportAny]

    usecase_response = SearchCampaignUsecaseImpl.GetSearchCampaignStatusResponse(
        search_campaign_id=SearchCampaignID.from_uuid(campaign_id),
        status=SearchCampaignStatus.ACTIVE,
        user_id="user_123",
        vacancy_id=vacancy_id,
        collected_current=10,
        daily_maximum=100,
        active_until=datetime.now(UTC),
    )

    hh_search_campaign_usecase.GetSearchCampaignStatusRequest = SearchCampaignUsecaseImpl.GetSearchCampaignStatusRequest
    hh_search_campaign_usecase.get_search_campaign_status = AsyncMock(return_value=usecase_response)

    await grpc_handler.GetSearchCampaignStatus(mock_stream)

    hh_search_campaign_usecase.get_search_campaign_status.assert_awaited_once()  # pyright: ignore[reportAny]

    mock_stream.send_message.assert_awaited_once()  # pyright: ignore[reportAny]
    sent_response = mock_stream.send_message.await_args[0][0]  # pyright: ignore[reportAny]
    assert isinstance(sent_response, hharon_pb2.GetSearchCampaignStatusResponse)
    assert sent_response.status == hharon_pb2.SEARCH_CAMPAIGN_STATUS_ACTIVE
    assert sent_response.vacancy_id == vacancy_id
    assert sent_response.collected_current == 10
    assert sent_response.collected_maximum == 100


@pytest.mark.asyncio
async def test_get_search_campaign_status_returns_not_exists(
    grpc_handler: HharonServiceHandler,
    hh_search_campaign_usecase: Mock,
    mock_stream: Mock,
) -> None:
    """Test that GetSearchCampaignStatus raises NOT_FOUND error when SearchCampaign does not exist."""
    vacancy_id = "vacancy_123"

    request = hharon_pb2.GetSearchCampaignStatusRequest(
        vacancy_id=vacancy_id,
    )

    mock_stream.recv_message.return_value = request  # pyright: ignore[reportAny]

    hh_search_campaign_usecase.get_search_campaign_status = AsyncMock(
        side_effect=SearchCampaignUsecaseNotFoundError("Search campaign not found")
    )
    hh_search_campaign_usecase.GetSearchCampaignStatusRequest = SearchCampaignUsecaseImpl.GetSearchCampaignStatusRequest

    with pytest.raises(grpclib.exceptions.GRPCError) as exc_info:
        await grpc_handler.GetSearchCampaignStatus(mock_stream)

    assert exc_info.value.status == GRPCStatus.NOT_FOUND
    hh_search_campaign_usecase.get_search_campaign_status.assert_awaited_once()  # pyright: ignore[reportAny]
    mock_stream.send_message.assert_not_awaited()  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_get_search_campaign_status_raises_internal_error(
    grpc_handler: HharonServiceHandler,
    hh_search_campaign_usecase: Mock,
    mock_stream: Mock,
) -> None:
    """Test that GetSearchCampaignStatus raises INTERNAL error on SearchCampaignUsecaseError."""
    vacancy_id = "vacancy_123"

    request = hharon_pb2.GetSearchCampaignStatusRequest(
        vacancy_id=vacancy_id,
    )

    mock_stream.recv_message.return_value = request  # pyright: ignore[reportAny]

    hh_search_campaign_usecase.get_search_campaign_status = AsyncMock(
        side_effect=SearchCampaignUsecaseError("Internal error")
    )

    with pytest.raises(grpclib.exceptions.GRPCError) as exc_info:
        await grpc_handler.GetSearchCampaignStatus(mock_stream)

    assert exc_info.value.status == GRPCStatus.INTERNAL
    hh_search_campaign_usecase.get_search_campaign_status.assert_awaited_once()  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_get_search_campaign_settings_returns_campaign_successfully(
    grpc_handler: HharonServiceHandler,
    hh_search_campaign_usecase: Mock,
    mock_stream: Mock,
) -> None:
    """Test that GetSearchCampaignSettings returns campaign successfully when SearchCampaign exists."""
    vacancy_id = "vacancy_123"

    request = hharon_pb2.GetSearchCampaignSettingsRequest(
        vacancy_id=vacancy_id,
    )

    mock_stream.recv_message.return_value = request  # pyright: ignore[reportAny]

    campaign_proto = hharon_pb2.SearchCampaign(
        user_id="user_123",
        vacancy_id=vacancy_id,
        daily_limit=30,
    )

    hh_search_campaign_usecase.GetSearchCampaignSettingsRequest = (
        SearchCampaignUsecaseImpl.GetSearchCampaignSettingsRequest
    )
    hh_search_campaign_usecase.get_search_campaign_settings = AsyncMock(return_value=campaign_proto)

    await grpc_handler.GetSearchCampaignSettings(mock_stream)

    hh_search_campaign_usecase.get_search_campaign_settings.assert_awaited_once()  # pyright: ignore[reportAny]

    mock_stream.send_message.assert_awaited_once()  # pyright: ignore[reportAny]
    sent_response = mock_stream.send_message.await_args[0][0]  # pyright: ignore[reportAny]
    assert isinstance(sent_response, hharon_pb2.GetSearchCampaignSettingsResponse)
    assert sent_response.campaign.user_id == "user_123"
    assert sent_response.campaign.vacancy_id == vacancy_id
    assert sent_response.campaign.daily_limit == 30


@pytest.mark.asyncio
async def test_get_search_campaign_settings_returns_not_exists(
    grpc_handler: HharonServiceHandler,
    hh_search_campaign_usecase: Mock,
    mock_stream: Mock,
) -> None:
    """Test that GetSearchCampaignSettings raises NOT_FOUND error when SearchCampaign does not exist."""
    vacancy_id = "vacancy_123"

    request = hharon_pb2.GetSearchCampaignSettingsRequest(
        vacancy_id=vacancy_id,
    )

    mock_stream.recv_message.return_value = request  # pyright: ignore[reportAny]

    hh_search_campaign_usecase.get_search_campaign_settings = AsyncMock(
        side_effect=SearchCampaignUsecaseNotFoundError("Search campaign not found")
    )
    hh_search_campaign_usecase.GetSearchCampaignSettingsRequest = (
        SearchCampaignUsecaseImpl.GetSearchCampaignSettingsRequest
    )

    with pytest.raises(grpclib.exceptions.GRPCError) as exc_info:
        await grpc_handler.GetSearchCampaignSettings(mock_stream)

    assert exc_info.value.status == GRPCStatus.NOT_FOUND
    hh_search_campaign_usecase.get_search_campaign_settings.assert_awaited_once()  # pyright: ignore[reportAny]
    mock_stream.send_message.assert_not_awaited()  # pyright: ignore[reportAny]
