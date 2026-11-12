from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from unittest.mock import AsyncMock, Mock

    from dishka.async_container import AsyncContainer

from hharon.protocols import oauth2 as oauth2_protocol
from hharon.usecases import oauth2 as oauth2_usecases


@pytest.mark.asyncio
async def test_exchange_secret_code_exchanges_code_for_tokens(
    exchange_secret_code_container: "AsyncContainer",
) -> None:
    """Test that exchange_secret_code successfully exchanges code for tokens."""
    usecase = await exchange_secret_code_container.get(oauth2_usecases.ExchangeSecretCode)
    assert isinstance(usecase, oauth2_usecases.ExchangeSecretCode)
    hh_adapter = cast("Mock", await exchange_secret_code_container.get(oauth2_protocol.OAuth2Protocol))
    encrypt_state_usecase = await exchange_secret_code_container.get(oauth2_usecases.EncryptOAuthState)

    user_id = "507f1f77bcf86cd799439011"
    secret_code = "test_secret_code"
    redirect_uri = "https://nanimai.tech/complete"
    access_token = "test_access_token"
    refresh_token = "test_refresh_token"
    expires_in = 3600

    # Encrypt state
    encrypted_state_response = encrypt_state_usecase.encrypt_oauth_state(
        oauth2_usecases.EncryptOAuthState.EncryptOAuthStateRequest(user_id=user_id)
    )
    encrypted_state = encrypted_state_response.state

    # Mock token response
    token_response = oauth2_protocol.OAuth2Protocol.TokenResponse(
        token=oauth2_protocol.Token(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
            token_type="Bearer",
        )
    )

    async def _get_token_by_secret_code(
        req: oauth2_protocol.OAuth2Protocol.GetTokensBySecretCodeRequest,
    ) -> oauth2_protocol.OAuth2Protocol.TokenResponse:
        assert req.secret_code == secret_code
        assert req.redirect_uri == redirect_uri
        return token_response

    # Mock's attributes are dynamically typed
    get_token_by_secret_code_mock = cast("AsyncMock", hh_adapter.get_token_by_secret_code)
    get_token_by_secret_code_mock.side_effect = _get_token_by_secret_code

    resp = await usecase.exchange_secret_code(
        oauth2_usecases.ExchangeSecretCode.ExchangeSecretCodeRequest(
            secret_code=secret_code,
            encrypted_state=encrypted_state,
            redirect_uri=redirect_uri,
        )
    )
    assert isinstance(resp, oauth2_usecases.ExchangeSecretCode.ExchangeSecretCodeResponse)

    # Verify response contains tokens
    assert resp.access_token == access_token
    assert resp.refresh_token == refresh_token
    assert resp.expires_in == expires_in


@pytest.mark.asyncio
async def test_exchange_secret_code_raises_error_on_empty_state(
    exchange_secret_code_container: "AsyncContainer",
) -> None:
    """Test that exchange_secret_code raises error on empty encrypted state."""
    usecase = await exchange_secret_code_container.get(oauth2_usecases.ExchangeSecretCode)

    secret_code = "test_secret_code"
    redirect_uri = "https://nanimai.tech/complete"
    empty_encrypted_state = ""

    with pytest.raises(oauth2_usecases.ExchangeSecretCodeInvalidStateError):
        _ = await usecase.exchange_secret_code(
            oauth2_usecases.ExchangeSecretCode.ExchangeSecretCodeRequest(
                secret_code=secret_code,
                encrypted_state=empty_encrypted_state,
                redirect_uri=redirect_uri,
            )
        )


@pytest.mark.asyncio
async def test_exchange_secret_code_raises_error_on_invalid_state(
    exchange_secret_code_container: "AsyncContainer",
) -> None:
    """Test that exchange_secret_code raises error on invalid encrypted state."""
    usecase = await exchange_secret_code_container.get(oauth2_usecases.ExchangeSecretCode)

    secret_code = "test_secret_code"
    redirect_uri = "https://nanimai.tech/complete"
    invalid_encrypted_state = "invalid_state"

    with pytest.raises(oauth2_usecases.ExchangeSecretCodeDecryptError):
        _ = await usecase.exchange_secret_code(
            oauth2_usecases.ExchangeSecretCode.ExchangeSecretCodeRequest(
                secret_code=secret_code,
                encrypted_state=invalid_encrypted_state,
                redirect_uri=redirect_uri,
            )
        )


@pytest.mark.asyncio
async def test_exchange_secret_code_raises_error_on_api_error(
    exchange_secret_code_container: "AsyncContainer",
) -> None:
    """Test that exchange_secret_code raises error on API error."""
    usecase = await exchange_secret_code_container.get(oauth2_usecases.ExchangeSecretCode)
    hh_adapter = cast("Mock", await exchange_secret_code_container.get(oauth2_protocol.OAuth2Protocol))
    encrypt_state_usecase = await exchange_secret_code_container.get(oauth2_usecases.EncryptOAuthState)

    user_id = "507f1f77bcf86cd799439011"
    secret_code = "test_secret_code"
    redirect_uri = "https://nanimai.tech/complete"

    # Encrypt state
    encrypted_state_response = encrypt_state_usecase.encrypt_oauth_state(
        oauth2_usecases.EncryptOAuthState.EncryptOAuthStateRequest(user_id=user_id)
    )
    encrypted_state = encrypted_state_response.state

    # Mock API error
    get_token_by_secret_code_mock = cast("AsyncMock", hh_adapter.get_token_by_secret_code)
    get_token_by_secret_code_mock.side_effect = oauth2_protocol.OAuth2APIError("API error")

    with pytest.raises(oauth2_usecases.ExchangeSecretCodeAPIError):
        _ = await usecase.exchange_secret_code(
            oauth2_usecases.ExchangeSecretCode.ExchangeSecretCodeRequest(
                secret_code=secret_code,
                encrypted_state=encrypted_state,
                redirect_uri=redirect_uri,
            )
        )


@pytest.mark.asyncio
async def test_exchange_secret_code_raises_error_on_validation_error(
    exchange_secret_code_container: "AsyncContainer",
) -> None:
    """Test that exchange_secret_code raises error on validation error."""
    usecase = await exchange_secret_code_container.get(oauth2_usecases.ExchangeSecretCode)
    hh_adapter = cast("Mock", await exchange_secret_code_container.get(oauth2_protocol.OAuth2Protocol))
    encrypt_state_usecase = await exchange_secret_code_container.get(oauth2_usecases.EncryptOAuthState)

    user_id = "507f1f77bcf86cd799439011"
    secret_code = "test_secret_code"
    redirect_uri = "https://nanimai.tech/complete"

    # Encrypt state
    encrypted_state_response = encrypt_state_usecase.encrypt_oauth_state(
        oauth2_usecases.EncryptOAuthState.EncryptOAuthStateRequest(user_id=user_id)
    )
    encrypted_state = encrypted_state_response.state

    # Mock validation error
    get_token_by_secret_code_mock = cast("AsyncMock", hh_adapter.get_token_by_secret_code)
    get_token_by_secret_code_mock.side_effect = oauth2_protocol.OAuth2ValidateError("validation error")

    with pytest.raises(oauth2_usecases.ExchangeSecretCodeAPIError) as exc_info:
        _ = await usecase.exchange_secret_code(
            oauth2_usecases.ExchangeSecretCode.ExchangeSecretCodeRequest(
                secret_code=secret_code,
                encrypted_state=encrypted_state,
                redirect_uri=redirect_uri,
            )
        )
    assert "validation" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_exchange_secret_code_raises_error_on_oauth2_error(
    exchange_secret_code_container: "AsyncContainer",
) -> None:
    """Test that exchange_secret_code raises error on general OAuth2 error."""
    usecase = await exchange_secret_code_container.get(oauth2_usecases.ExchangeSecretCode)
    hh_adapter = cast("Mock", await exchange_secret_code_container.get(oauth2_protocol.OAuth2Protocol))
    encrypt_state_usecase = await exchange_secret_code_container.get(oauth2_usecases.EncryptOAuthState)

    user_id = "507f1f77bcf86cd799439011"
    secret_code = "test_secret_code"
    redirect_uri = "https://nanimai.tech/complete"

    # Encrypt state
    encrypted_state_response = encrypt_state_usecase.encrypt_oauth_state(
        oauth2_usecases.EncryptOAuthState.EncryptOAuthStateRequest(user_id=user_id)
    )
    encrypted_state = encrypted_state_response.state

    # Mock general OAuth2 error
    get_token_by_secret_code_mock = cast("AsyncMock", hh_adapter.get_token_by_secret_code)
    get_token_by_secret_code_mock.side_effect = oauth2_protocol.OAuth2Error("general error")

    with pytest.raises(oauth2_usecases.ExchangeSecretCodeAPIError):
        _ = await usecase.exchange_secret_code(
            oauth2_usecases.ExchangeSecretCode.ExchangeSecretCodeRequest(
                secret_code=secret_code,
                encrypted_state=encrypted_state,
                redirect_uri=redirect_uri,
            )
        )


@pytest.mark.asyncio
async def test_exchange_secret_code_handles_empty_secret_code(
    exchange_secret_code_container: "AsyncContainer",
) -> None:
    """Test that exchange_secret_code handles empty secret code gracefully."""
    usecase = await exchange_secret_code_container.get(oauth2_usecases.ExchangeSecretCode)
    hh_adapter = cast("Mock", await exchange_secret_code_container.get(oauth2_protocol.OAuth2Protocol))
    encrypt_state_usecase = await exchange_secret_code_container.get(oauth2_usecases.EncryptOAuthState)

    user_id = "507f1f77bcf86cd799439011"
    secret_code = ""
    redirect_uri = "https://nanimai.tech/complete"

    # Encrypt state
    encrypted_state_response = encrypt_state_usecase.encrypt_oauth_state(
        oauth2_usecases.EncryptOAuthState.EncryptOAuthStateRequest(user_id=user_id)
    )
    encrypted_state = encrypted_state_response.state

    # Mock API error for empty code
    get_token_by_secret_code_mock = cast("AsyncMock", hh_adapter.get_token_by_secret_code)
    get_token_by_secret_code_mock.side_effect = oauth2_protocol.OAuth2APIError("invalid code")

    with pytest.raises(oauth2_usecases.ExchangeSecretCodeAPIError):
        _ = await usecase.exchange_secret_code(
            oauth2_usecases.ExchangeSecretCode.ExchangeSecretCodeRequest(
                secret_code=secret_code,
                encrypted_state=encrypted_state,
                redirect_uri=redirect_uri,
            )
        )
