from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from google.protobuf.timestamp_pb2 import Timestamp

from hharon.infra.resume_search_scan import ResumeSearchScanConfig, ResumeSearchScanInitialDelayConstant
from hharon.protocols.resume_search_scan import (
    HeadHunterAccessDeniedError,
    HeadHunterRateLimitError,
    HeadHunterResumeSearchScanError,
)
from hharon.usecases.hh_search_campaign.mapper import SearchCampaignMapperUsecase
from hharon.usecases.resume_search_scan import (
    GetSearchCampaignPreviewAccessDeniedError,
    GetSearchCampaignPreviewError,
    GetSearchCampaignPreviewRateLimitError,
    GetSearchCampaignPreviewUsecase,
)
from hharon.usecases.token.get_tokens import GetTokens, GetTokensError
from hharon_api.v1 import hharon_pb2


def _make_campaign_proto(*, user_id: str = "user_123", daily_limit: int = 30) -> hharon_pb2.SearchCampaign:
    campaign = hharon_pb2.SearchCampaign(
        user_id=user_id,
        vacancy_id="vacancy_123",
        daily_limit=daily_limit,
        text=[hharon_pb2.SearchCampaign.FullTextFilter(text="python developer")],
    )
    ts = Timestamp()
    ts.FromDatetime(datetime(2025, 3, 1, 0, 0, 0, tzinfo=UTC))
    campaign.active_until.CopyFrom(ts)
    return campaign


@pytest.fixture
def mock_hh_client() -> Mock:
    client = Mock()
    client.get_resume_search_count = AsyncMock(return_value=150)
    return client


@pytest.fixture
def mock_get_tokens() -> Mock:
    tokens = Mock(spec=GetTokens)
    tokens.get_tokens = AsyncMock(
        return_value=GetTokens.GetTokensResponse(
            access_token="token_123",
            refresh_token="refresh_123",
            expires_at=datetime.now(UTC),
            token_type="Bearer",
            is_invalid=False,
        )
    )
    return tokens


@pytest.fixture
def mock_cache() -> Mock:
    cache = Mock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=None)
    return cache


@pytest.fixture
def config() -> ResumeSearchScanConfig:
    return ResumeSearchScanConfig(
        scans_per_day=3,
        initial_delay=ResumeSearchScanInitialDelayConstant(value=timedelta(minutes=1)),
    )


@pytest.fixture
def usecase(
    mock_hh_client: Mock,
    mock_get_tokens: Mock,
    mock_cache: Mock,
    config: ResumeSearchScanConfig,
) -> GetSearchCampaignPreviewUsecase:
    return GetSearchCampaignPreviewUsecase(
        _hh_client=mock_hh_client,
        _get_tokens=mock_get_tokens,
        _cache=mock_cache,
        _config=config,
        _mapper=SearchCampaignMapperUsecase(),
    )


@pytest.mark.asyncio
async def test_get_preview_returns_response_successfully(
    usecase: GetSearchCampaignPreviewUsecase,
    mock_hh_client: Mock,
    mock_cache: Mock,
) -> None:
    """Test that get_preview returns correct response when HH API succeeds."""
    campaign = _make_campaign_proto(user_id="user_123", daily_limit=30)

    response = await usecase.get_preview(GetSearchCampaignPreviewUsecase.GetPreviewRequest(campaign=campaign))

    assert response.total_candidates == 150
    assert response.interval_seconds == 28800  # 24h / 3 = 8h
    assert response.candidates_per_run == 10  # ceil(30 / 3)

    mock_hh_client.get_resume_search_count.assert_awaited_once()
    mock_cache.set.assert_awaited_once()
    call_args = mock_cache.set.await_args
    assert "search_campaign_preview:user_123:" in call_args[0][0]
    assert call_args[0][1].total_candidates == 150


@pytest.mark.asyncio
async def test_get_preview_returns_cached_response(
    usecase: GetSearchCampaignPreviewUsecase,
    mock_hh_client: Mock,
    mock_cache: Mock,
) -> None:
    """Test that get_preview returns cached response on cache hit."""
    campaign = _make_campaign_proto()
    cached = GetSearchCampaignPreviewUsecase.GetPreviewResponse(
        total_candidates=99,
        interval_seconds=28800,
        candidates_per_run=10,
    )
    mock_cache.get = AsyncMock(return_value=cached)

    response = await usecase.get_preview(GetSearchCampaignPreviewUsecase.GetPreviewRequest(campaign=campaign))

    assert response.total_candidates == 99
    assert response.interval_seconds == 28800
    assert response.candidates_per_run == 10
    mock_hh_client.get_resume_search_count.assert_not_awaited()
    mock_cache.set.assert_not_awaited()
    mock_cache.get.assert_awaited_once()
    call_args = mock_cache.get.await_args
    assert "search_campaign_preview:user_123:" in call_args[0][0]
    assert call_args[1]["unmarshal_as"] == GetSearchCampaignPreviewUsecase.GetPreviewResponse


@pytest.mark.asyncio
async def test_get_preview_raises_when_campaign_none(
    usecase: GetSearchCampaignPreviewUsecase,
) -> None:
    """Test that get_preview raises when campaign is None."""
    with pytest.raises(GetSearchCampaignPreviewError) as exc_info:
        await usecase.get_preview(GetSearchCampaignPreviewUsecase.GetPreviewRequest(campaign=None))

    assert "campaign is required" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_preview_raises_when_user_id_empty(
    usecase: GetSearchCampaignPreviewUsecase,
) -> None:
    """Test that get_preview raises when user_id is empty."""
    campaign = _make_campaign_proto()
    campaign.user_id = ""

    with pytest.raises(GetSearchCampaignPreviewError) as exc_info:
        await usecase.get_preview(GetSearchCampaignPreviewUsecase.GetPreviewRequest(campaign=campaign))

    assert "user_id is required" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_preview_raises_access_denied_on_get_tokens_error(
    usecase: GetSearchCampaignPreviewUsecase,
    mock_get_tokens: Mock,
) -> None:
    """Test that get_preview raises GetSearchCampaignPreviewAccessDeniedError on GetTokensError."""
    campaign = _make_campaign_proto()
    mock_get_tokens.get_tokens = AsyncMock(side_effect=GetTokensError("no tokens"))

    with pytest.raises(GetSearchCampaignPreviewAccessDeniedError):
        await usecase.get_preview(GetSearchCampaignPreviewUsecase.GetPreviewRequest(campaign=campaign))


@pytest.mark.asyncio
async def test_get_preview_raises_access_denied_on_hh_access_denied(
    usecase: GetSearchCampaignPreviewUsecase,
    mock_hh_client: Mock,
) -> None:
    """Test that get_preview raises GetSearchCampaignPreviewAccessDeniedError on HH access denied."""

    campaign = _make_campaign_proto()
    mock_hh_client.get_resume_search_count = AsyncMock(side_effect=HeadHunterAccessDeniedError("access denied"))

    with pytest.raises(GetSearchCampaignPreviewAccessDeniedError):
        await usecase.get_preview(GetSearchCampaignPreviewUsecase.GetPreviewRequest(campaign=campaign))


@pytest.mark.asyncio
async def test_get_preview_raises_error_on_hh_resume_search_scan_error(
    usecase: GetSearchCampaignPreviewUsecase,
    mock_hh_client: Mock,
) -> None:
    """Test that get_preview raises GetSearchCampaignPreviewError on HH API error."""

    campaign = _make_campaign_proto()
    mock_hh_client.get_resume_search_count = AsyncMock(side_effect=HeadHunterResumeSearchScanError("api error"))

    with pytest.raises(GetSearchCampaignPreviewError):
        await usecase.get_preview(GetSearchCampaignPreviewUsecase.GetPreviewRequest(campaign=campaign))


@pytest.mark.asyncio
async def test_get_preview_raises_on_rate_limit(
    usecase: GetSearchCampaignPreviewUsecase,
    mock_hh_client: Mock,
) -> None:
    """Test that get_preview raises GetSearchCampaignPreviewRateLimitError on HH rate limit (429)."""
    campaign = _make_campaign_proto()
    mock_hh_client.get_resume_search_count = AsyncMock(
        side_effect=HeadHunterRateLimitError("Rate limit exceeded", retry_after=60)
    )

    with pytest.raises(GetSearchCampaignPreviewRateLimitError) as exc_info:
        await usecase.get_preview(GetSearchCampaignPreviewUsecase.GetPreviewRequest(campaign=campaign))

    assert exc_info.value.retry_after == 60
