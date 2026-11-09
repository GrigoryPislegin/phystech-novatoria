from unittest.mock import AsyncMock, Mock

import pytest
from grpclib.server import Stream

from hharon.usecases import (
    GetHeadhunterVacancyUsecase,
    ProxyHeadhunterSuggestions,
    response_collection,
    resume_search_scan,
)
from hharon.usecases.hh_manager_access import GetHHSearchCampaignAccessUsecase
from hharon.usecases.hh_search_campaign import ExtractSearchCampaignFromURL, SearchCampaignUsecase
from hharon.usecases.oauth2 import CompleteOauthFlow, InitOAuthFlow
from hharon.usecases.response_collection import GetResponseCollectionPreviewUsecase
from hharon.usecases.resume_search_scan import GetSearchCampaignPreviewUsecase
from hharon.usecases.user import GetHharonUser
from hharon_api.v1 import hharon_pb2


@pytest.fixture
def init_oauth_flow_usecase() -> Mock:
    """Fixture to create mock InitOAuthFlow usecase."""
    return Mock(spec=InitOAuthFlow)


@pytest.fixture
def complete_oauth_flow_usecase() -> Mock:
    """Fixture to create mock CompleteOauthFlow usecase."""
    return Mock(spec=CompleteOauthFlow)


@pytest.fixture
def get_user_usecase() -> Mock:
    return Mock(spec=GetHharonUser)


@pytest.fixture
def init_response_collection_usecase() -> Mock:
    """Fixture to create mock InitResponseCollection usecase."""
    return Mock(spec=response_collection.InitResponseCollection)


@pytest.fixture
def init_search_campaign_execution_usecase() -> Mock:
    """Fixture to create mock InitSearchCampaignExecution usecase."""
    return Mock(spec=resume_search_scan.InitSearchCampaignExecution)


@pytest.fixture
def complete_search_campaign_execution_usecase() -> Mock:
    """Fixture to create mock CompleteSearchCampaignExecution usecase."""
    return Mock(spec=resume_search_scan.CompleteSearchCampaignExecution)


@pytest.fixture
def get_response_collection_preview_usecase() -> Mock:
    return Mock(spec=GetResponseCollectionPreviewUsecase)


@pytest.fixture
def hh_search_campaign_usecase() -> Mock:
    """Fixture to create mock SearchCampaignUsecase."""
    return Mock(spec=SearchCampaignUsecase)


@pytest.fixture
def get_manager_access_usecase() -> Mock:
    """Fixture to create mock GetHHSearchCampaignAccessUsecase."""
    return Mock(spec=GetHHSearchCampaignAccessUsecase)


@pytest.fixture
def get_vacancy_usecase() -> Mock:
    """Fixture to create mock GetHeadhunterVacancyUsecase."""
    return Mock(spec=GetHeadhunterVacancyUsecase)


@pytest.fixture
def proxy_headhunter_suggestions_usecase() -> Mock:
    """Fixture to create mock ProxyHeadhunterSuggestions usecase."""
    return Mock(spec=ProxyHeadhunterSuggestions)


@pytest.fixture
def mock_stream() -> Mock:
    stream = Mock(spec=Stream)
    stream.recv_message = AsyncMock()
    stream.send_message = AsyncMock()
    return stream


@pytest.fixture
def complete_response_collection_usecase() -> Mock:
    """Fixture to create mock CompleteResponseCollection usecase."""
    return Mock(spec=response_collection.CompleteResponseCollection)


@pytest.fixture
def get_search_campaign_preview_usecase() -> Mock:
    """Fixture to create mock GetSearchCampaignPreviewUsecase."""
    return Mock(spec=GetSearchCampaignPreviewUsecase)


@pytest.fixture
def extract_search_campaign_usecase() -> Mock:
    """Fixture to create mock ExtractSearchCampaignFromURL usecase."""
    return Mock(spec=ExtractSearchCampaignFromURL)


@pytest.fixture
def get_user_request() -> hharon_pb2.GetUserRequest:
    return hharon_pb2.GetUserRequest(user_id="some_id")
