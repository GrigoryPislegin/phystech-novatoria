# pyright: reportAny=false
from unittest.mock import AsyncMock

import pytest
from dishka import AsyncContainer
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.usecases.hh_manager_access.usecase import (
    GetHHSearchCampaignAccessUsecase,
    GetManagerAccessUsecaseTokenError,
    GetManagerAccessUsecaseUserError,
)
from hharon.usecases.token.get_tokens import GetTokensError
from hharon.usecases.user.get_user import GetHharonUserError


@pytest.mark.asyncio
async def test_get_manager_access_token_error(setup_get_manager_access_container: AsyncContainer) -> None:
    """Test manager access with token error."""
    usecase = await setup_get_manager_access_container.get(GetHHSearchCampaignAccessUsecase[AsyncSession])

    # Mock token error
    usecase._get_tokens_usecase.get_tokens = AsyncMock(side_effect=GetTokensError("Token error"))

    request = GetHHSearchCampaignAccessUsecase.GetHHSearchCampaignAccessRequest(user_id="user123")

    with pytest.raises(GetManagerAccessUsecaseTokenError):
        await usecase.get_headhunter_search_campaign_access(request)


@pytest.mark.asyncio
async def test_get_manager_access_user_error(setup_get_manager_access_container: AsyncContainer) -> None:
    """Test manager access with user error."""
    usecase = await setup_get_manager_access_container.get(GetHHSearchCampaignAccessUsecase[AsyncSession])

    # Mock user error
    usecase._get_user_usecase.get_user = AsyncMock(side_effect=GetHharonUserError("User error"))

    request = GetHHSearchCampaignAccessUsecase.GetHHSearchCampaignAccessRequest(user_id="user123")

    with pytest.raises(GetManagerAccessUsecaseUserError):
        await usecase.get_headhunter_search_campaign_access(request)
