from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer

    from hharon.domain.token import TokenPair
    from hharon.domain.user import HharonUser

from hharon.domain.token import TokenPair
from hharon.domain.user import HharonUser
from hharon.protocols import cache as cache_protocol
from hharon.protocols import oauth2 as oauth2_protocol
from hharon.protocols import token as token_protocol
from hharon.protocols import user as user_protocol
from hharon.usecases.crypt import CipherUsecase
from hharon.usecases.oauth2 import CompleteOauthFlow, EncryptOAuthState, ExchangeSecretCode
from hharon.usecases.outbox_task.schedulers import token_update_scheduler


@pytest.mark.asyncio
async def test_complete_oauth_flow_completes_flow_successfully(
    complete_oauth_flow_container: "AsyncContainer",
    mock_exchange_secret_code_response: "ExchangeSecretCode.ExchangeSecretCodeResponse",
    mock_user_info_response: oauth2_protocol.OAuth2UserInfoProtocol.GetCurrentUserInfoResponse,
    mock_created_user: "HharonUser",
    mock_token_pair: "TokenPair",
) -> None:
    """Test that complete_oauth_flow successfully completes the OAuth flow."""
    usecase = await complete_oauth_flow_container.get(CompleteOauthFlow[AsyncSession])
    assert isinstance(usecase, CompleteOauthFlow)

    encrypt_state_usecase = await complete_oauth_flow_container.get(EncryptOAuthState)
    exchange_secret_code_usecase = cast("Mock", await complete_oauth_flow_container.get(ExchangeSecretCode))
    hh_user_info_adapter = cast("Mock", await complete_oauth_flow_container.get(oauth2_protocol.OAuth2UserInfoProtocol))
    user_repository = cast(
        "Mock",
        await complete_oauth_flow_container.get(user_protocol.HharonUserRepositoryProtocol[AsyncSession]),
    )
    token_repository = cast(
        "Mock",
        await complete_oauth_flow_container.get(token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession]),
    )
    cipher_usecase = cast("Mock", await complete_oauth_flow_container.get(CipherUsecase))

    # Setup test data
    user_id = "507f1f77bcf86cd799439011"
    secret_code = "test_secret_code"
    redirect_uri = "https://nanimai.tech/complete"
    access_token = mock_exchange_secret_code_response.access_token

    # Encrypt state
    encrypted_state_response = encrypt_state_usecase.encrypt_oauth_state(
        EncryptOAuthState.EncryptOAuthStateRequest(user_id=user_id)
    )
    encrypted_state = encrypted_state_response.state

    # Setup ExchangeSecretCode mock
    exchange_mock = cast("AsyncMock", exchange_secret_code_usecase.exchange_secret_code)
    exchange_mock.return_value = mock_exchange_secret_code_response

    # Setup OAuth2UserInfoProtocol mock
    user_info_mock = cast("AsyncMock", hh_user_info_adapter.get_current_user_info)
    user_info_mock.return_value = mock_user_info_response

    # Setup UserRepository mock
    session_mock = Mock()

    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        yield session_mock

    user_repository.context = _context

    async def _get_user(
        _session: Mock,
        _request: user_protocol.HharonUserRepositoryProtocol.GetUserRequest,
    ) -> "HharonUser | None":
        return None  # User doesn't exist (new user flow)

    user_repository.get_user = AsyncMock(side_effect=_get_user)

    async def _get_user_by_hh_manager_id(
        _session: Mock,
        _request: user_protocol.HharonUserRepositoryProtocol.GetUserByHhIdRequest,
    ) -> "HharonUser | None":
        return None  # User doesn't exist

    user_repository.get_user_by_hh_manager_id = AsyncMock(side_effect=_get_user_by_hh_manager_id)

    async def _create_user(
        _session: Mock,
        _request: user_protocol.HharonUserRepositoryProtocol.CreateUserRequest,
    ) -> "HharonUser":
        return mock_created_user

    user_repository.create_user = AsyncMock(side_effect=_create_user)

    # Setup CipherUsecase mock
    cipher_encrypt_mock = cast("Mock", cipher_usecase.encrypt_bytes)
    cipher_encrypt_mock.return_value = CipherUsecase.EncryptBytesResponse(data=b"encrypted_token")

    # Setup TokenRepository mock
    token_repository.save_tokens = AsyncMock(return_value=mock_token_pair)

    token_update_scheduler_mock = cast(
        "Mock",
        await complete_oauth_flow_container.get(token_update_scheduler.TokenUpdateScheduler[AsyncSession]),
    )
    token_update_scheduler_mock.schedule = AsyncMock()

    # Execute usecase
    response = await usecase.complete_oauth_flow(
        CompleteOauthFlow.CompleteOauthFlowRequest(
            secret_code=secret_code,
            encrypted_state=encrypted_state,
            redirect_uri=redirect_uri,
        )
    )

    # Verify response
    assert isinstance(response, CompleteOauthFlow.CompleteOauthFlowResponse)
    assert response.success is True

    # Verify all mocks were called
    exchange_mock.assert_awaited_once()
    user_info_mock.assert_awaited_once()
    user_repository.get_user.assert_awaited_once()  # pyright: ignore[reportAny]
    user_repository.get_user_by_hh_manager_id.assert_awaited_once()  # pyright: ignore[reportAny]
    user_repository.create_user.assert_awaited_once()  # pyright: ignore[reportAny]
    assert cipher_encrypt_mock.call_count == 2  # Called for access_token and refresh_token
    token_repository.save_tokens.assert_awaited_once()  # pyright: ignore[reportAny]
    token_update_scheduler_mock.schedule.assert_awaited_once()  # pyright: ignore[reportAny]

    # Verify user_info was called with correct access_token
    assert user_info_mock.await_args is not None
    user_info_call_args = user_info_mock.await_args[0][0]  # pyright: ignore[reportAny]
    assert user_info_call_args.access_token == access_token  # pyright: ignore[reportAny]

    # Verify token_repository.save_tokens was called with correct data
    assert token_repository.save_tokens.await_args is not None  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_complete_oauth_flow_re_auth_updates_user_and_tokens(
    complete_oauth_flow_container: "AsyncContainer",
    mock_exchange_secret_code_response: "ExchangeSecretCode.ExchangeSecretCodeResponse",
    mock_user_info_response: oauth2_protocol.OAuth2UserInfoProtocol.GetCurrentUserInfoResponse,
    mock_created_user: "HharonUser",
    mock_token_pair: "TokenPair",
) -> None:
    """Test that complete_oauth_flow on re-auth updates user, tokens, cancels pending tasks."""
    usecase = await complete_oauth_flow_container.get(CompleteOauthFlow[AsyncSession])
    exchange_secret_code_usecase = cast("Mock", await complete_oauth_flow_container.get(ExchangeSecretCode))
    hh_user_info_adapter = cast("Mock", await complete_oauth_flow_container.get(oauth2_protocol.OAuth2UserInfoProtocol))
    user_repository = cast(
        "Mock",
        await complete_oauth_flow_container.get(user_protocol.HharonUserRepositoryProtocol[AsyncSession]),
    )
    token_repository = cast(
        "Mock",
        await complete_oauth_flow_container.get(token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession]),
    )
    cipher_usecase = cast("Mock", await complete_oauth_flow_container.get(CipherUsecase))

    user_id = "507f1f77bcf86cd799439011"
    encrypt_state_usecase = await complete_oauth_flow_container.get(EncryptOAuthState)
    encrypted_state_response = encrypt_state_usecase.encrypt_oauth_state(
        EncryptOAuthState.EncryptOAuthStateRequest(user_id=user_id)
    )

    exchange_secret_code_usecase.exchange_secret_code = AsyncMock(return_value=mock_exchange_secret_code_response)
    hh_user_info_adapter.get_current_user_info = AsyncMock(return_value=mock_user_info_response)

    session_mock = Mock()

    @asynccontextmanager
    async def _context() -> AsyncIterator[Mock]:
        yield session_mock

    user_repository.context = _context

    # Re-auth: user exists by user_id
    async def _get_user(
        _session: Mock,
        _request: user_protocol.HharonUserRepositoryProtocol.GetUserRequest,
    ) -> HharonUser | None:
        return mock_created_user

    user_repository.get_user = AsyncMock(side_effect=_get_user)

    updated_user = HharonUser(
        user_id=mock_created_user.user_id,
        hh_manager_id="999999",  # New HH account
        hh_employer_id="888888",
        name=mock_user_info_response.name,
        email=mock_user_info_response.email,
    )

    async def _update_user(
        _session: Mock,
        request: user_protocol.HharonUserRepositoryProtocol.UpdateUserRequest,
    ) -> HharonUser:
        assert request.hh_manager_id == mock_user_info_response.hh_manager_id
        assert request.hh_employer_id == mock_user_info_response.hh_employer_id
        return updated_user

    user_repository.update_user = AsyncMock(side_effect=_update_user)

    updated_token_pair = TokenPair(
        user_id=mock_created_user.user_id,
        encrypted_access_token=b"encrypted_access",
        encrypted_refresh_token=b"encrypted_refresh",
        expires_at=mock_token_pair.expires_at,
        token_type="bearer",
        is_invalid=False,
    )

    async def _update_tokens(
        _session: Mock,
        _request: token_protocol.HeadHunterTokenRepositoryProtocol.UpdateTokensRequest,
    ) -> TokenPair:
        return updated_token_pair

    token_repository.update_tokens = AsyncMock(side_effect=_update_tokens)

    cipher_usecase.encrypt_bytes = Mock(return_value=CipherUsecase.EncryptBytesResponse(data=b"encrypted_token"))

    scheduler_mock = cast(
        "Mock",
        await complete_oauth_flow_container.get(token_update_scheduler.TokenUpdateScheduler[AsyncSession]),
    )
    scheduler_mock.schedule = AsyncMock()
    scheduler_mock.cancel_pending_for_user = AsyncMock(return_value=2)

    cache_mock = cast(
        "Mock",
        await complete_oauth_flow_container.get(cache_protocol.CacheProtocol),
    )

    response = await usecase.complete_oauth_flow(
        CompleteOauthFlow.CompleteOauthFlowRequest(
            secret_code="test_code",
            encrypted_state=encrypted_state_response.state,
            redirect_uri="https://nanimai.tech/complete",
        )
    )

    assert response.success is True
    assert response.user_id == mock_created_user.user_id

    user_repository.get_user.assert_awaited_once()
    user_repository.update_user.assert_awaited_once()
    token_repository.update_tokens.assert_awaited_once()
    token_repository.save_tokens.assert_not_called()
    scheduler_mock.cancel_pending_for_user.assert_awaited_once()
    scheduler_mock.schedule.assert_awaited_once()
    cache_mock.delete.assert_awaited_once_with(f"hharon:user:{mock_created_user.user_id}")
