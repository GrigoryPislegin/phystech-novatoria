from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.domain.outbox_task import OutboxTask, OutboxTaskStatus, OutboxTaskType, TokenUpdatePayload
from hharon.domain.scalars import TaskID
from hharon.domain.token import TokenPair
from hharon.protocols import oauth2 as oauth2_protocol
from hharon.protocols import token as token_protocol
from hharon.usecases.crypt import CipherUsecase
from hharon.usecases.outbox_task.handlers import token_update_handler
from hharon.usecases.outbox_task.schedulers import token_update_scheduler
from hharon.usecases.outbox_task.usecase import OutboxContext

if TYPE_CHECKING:
    from dishka.async_container import AsyncContainer


@pytest.mark.asyncio
async def test_handle_processes_token_refresh_successfully(
    token_update_handler_container: "AsyncContainer",
    mock_token_repository: "Mock",
    mock_oauth2_adapter: "Mock",
    cipher_usecase: CipherUsecase,
) -> None:
    """Test that handle successfully processes token refresh."""
    handler = await token_update_handler_container.get(token_update_handler.TokenUpdateHandler[AsyncSession])
    assert isinstance(handler, token_update_handler.TokenUpdateHandler)

    token_repository = mock_token_repository
    hh_oauth2_adapter = mock_oauth2_adapter
    handler_scheduler = cast(
        "Mock",
        await token_update_handler_container.get(token_update_scheduler.TokenUpdateScheduler[AsyncSession]),
    )

    user_id = "user123"
    task_id = TaskID.from_uuid(uuid4())
    old_refresh_token = "old_refresh_token"
    new_access_token = "new_access_token"
    new_refresh_token = "new_refresh_token"
    new_expires_in = 7200

    # Create task
    payload = TokenUpdatePayload(user_id=user_id)
    task = OutboxTask(
        id=task_id,
        task_type=OutboxTaskType.TOKEN_UPDATE,
        payload=payload.model_dump(mode="json"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        available_at=datetime.now(UTC),
        attempts=0,
        status=OutboxTaskStatus.PENDING,
    )

    # Create context
    session = Mock()
    ctx = OutboxContext[AsyncSession](session=session)

    # Encrypt old refresh token
    encrypt_old_refresh_response = cipher_usecase.encrypt_bytes(
        CipherUsecase.EncryptBytesRequest(data=old_refresh_token.encode("utf-8"))
    )

    expires_at = datetime.now(UTC) + timedelta(seconds=3600)
    old_token_pair = TokenPair(
        user_id=user_id,
        encrypted_access_token=b"old_encrypted_access",
        encrypted_refresh_token=encrypt_old_refresh_response.data,
        expires_at=expires_at,
        token_type="bearer",
        is_invalid=False,
    )

    # Mock OAuth2 response
    new_expires_at = datetime.now(UTC) + timedelta(seconds=new_expires_in)
    token_response = oauth2_protocol.OAuth2Protocol.TokenResponse(
        token=oauth2_protocol.Token(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_in=new_expires_in,
            expires_at=new_expires_at,
            token_type="bearer",
        )
    )

    token_repository.lock_tokens_for_update = AsyncMock(return_value=old_token_pair)
    hh_oauth2_adapter.refresh_tokens = AsyncMock(return_value=token_response)

    def _update_tokens(
        _session: Mock, request: token_protocol.HeadHunterTokenRepositoryProtocol.UpdateTokensRequest
    ) -> TokenPair:
        return TokenPair(
            user_id=request.user_id,
            encrypted_access_token=request.encrypted_access_token,
            encrypted_refresh_token=request.encrypted_refresh_token,
            expires_at=request.expires_at,
            token_type=request.token_type,
            is_invalid=request.is_invalid or False,
        )

    token_repository.update_tokens = AsyncMock(side_effect=_update_tokens)
    handler_scheduler.schedule = AsyncMock()

    await handler.handle(ctx=ctx, task=task)

    token_repository.lock_tokens_for_update.assert_awaited_once()  # pyright: ignore[reportAny]
    hh_oauth2_adapter.refresh_tokens.assert_awaited_once()  # pyright: ignore[reportAny]
    token_repository.update_tokens.assert_awaited_once()  # pyright: ignore[reportAny]
    handler_scheduler.schedule.assert_awaited_once()  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_handle_raises_error_when_payload_invalid(
    token_update_handler_container: "AsyncContainer",
) -> None:
    """Test that handle raises error when task payload is invalid."""
    handler = await token_update_handler_container.get(token_update_handler.TokenUpdateHandler[AsyncSession])

    task_id = TaskID.from_uuid(uuid4())
    task = OutboxTask(
        id=task_id,
        task_type=OutboxTaskType.TOKEN_UPDATE,
        payload={"invalid": "payload"},  # Invalid payload
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        available_at=datetime.now(UTC),
        attempts=0,
        status=OutboxTaskStatus.PENDING,
    )

    session = Mock()
    ctx = OutboxContext[AsyncSession](session=session)

    with pytest.raises(token_update_handler.TokenUpdateHandlerError):
        await handler.handle(ctx=ctx, task=task)


@pytest.mark.asyncio
async def test_handle_raises_error_when_tokens_not_found(
    token_update_handler_container: "AsyncContainer",
    mock_token_repository: "Mock",
) -> None:
    """Test that handle raises error when tokens are not found."""
    handler = await token_update_handler_container.get(token_update_handler.TokenUpdateHandler[AsyncSession])
    token_repository = mock_token_repository

    user_id = "user123"

    payload = TokenUpdatePayload(user_id=user_id)
    task = OutboxTask(
        id=TaskID.from_uuid(uuid4()),
        task_type=OutboxTaskType.TOKEN_UPDATE,
        payload=payload.model_dump(mode="json"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        available_at=datetime.now(UTC),
        attempts=0,
        status=OutboxTaskStatus.PENDING,
    )

    session = Mock()
    ctx = OutboxContext[AsyncSession](session=session)

    token_repository.lock_tokens_for_update = AsyncMock(return_value=None)

    with pytest.raises(token_update_handler.TokenUpdateHandlerNotFoundError):
        await handler.handle(ctx=ctx, task=task)


@pytest.mark.asyncio
async def test_handle_raises_error_when_tokens_invalid(
    token_update_handler_container: "AsyncContainer",
    mock_token_repository: "Mock",
) -> None:
    """Test that handle raises error when tokens are invalid."""
    handler = await token_update_handler_container.get(token_update_handler.TokenUpdateHandler[AsyncSession])
    token_repository = mock_token_repository

    user_id = "user123"
    payload = TokenUpdatePayload(user_id=user_id)
    task = OutboxTask(
        id=TaskID.from_uuid(uuid4()),
        task_type=OutboxTaskType.TOKEN_UPDATE,
        payload=payload.model_dump(mode="json"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        available_at=datetime.now(UTC),
        attempts=0,
        status=OutboxTaskStatus.PENDING,
    )

    session = Mock()
    ctx = OutboxContext[AsyncSession](session=session)

    invalid_token_pair = TokenPair(
        user_id=user_id,
        encrypted_access_token=b"encrypted",
        encrypted_refresh_token=b"encrypted",
        expires_at=datetime.now(UTC),
        token_type="bearer",
        is_invalid=True,  # Invalid tokens
    )

    token_repository.lock_tokens_for_update = AsyncMock(return_value=invalid_token_pair)

    with pytest.raises(token_update_handler.TokenUpdateHandlerNotFoundError):
        await handler.handle(ctx=ctx, task=task)


@pytest.mark.asyncio
async def test_handle_raises_error_on_decrypt_error(
    token_update_handler_container: "AsyncContainer",
    mock_token_repository: "Mock",
) -> None:
    """Test that handle raises error when decryption fails."""
    handler = await token_update_handler_container.get(token_update_handler.TokenUpdateHandler[AsyncSession])
    token_repository = mock_token_repository

    user_id = "user123"
    payload = TokenUpdatePayload(user_id=user_id)
    task = OutboxTask(
        id=TaskID.from_uuid(uuid4()),
        task_type=OutboxTaskType.TOKEN_UPDATE,
        payload=payload.model_dump(mode="json"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        available_at=datetime.now(UTC),
        attempts=0,
        status=OutboxTaskStatus.PENDING,
    )

    session = Mock()
    ctx = OutboxContext[AsyncSession](session=session)

    # Create token pair with invalid encrypted data
    invalid_token_pair = TokenPair(
        user_id=user_id,
        encrypted_access_token=b"old_encrypted_access",
        encrypted_refresh_token=b"invalid_encrypted_data",  # Invalid encrypted data
        expires_at=datetime.now(UTC),
        token_type="bearer",
        is_invalid=False,
    )

    token_repository.lock_tokens_for_update = AsyncMock(return_value=invalid_token_pair)

    with pytest.raises(token_update_handler.TokenUpdateHandlerDecryptError):
        await handler.handle(ctx=ctx, task=task)


@pytest.mark.asyncio
async def test_handle_raises_error_on_oauth_api_error(
    token_update_handler_container: "AsyncContainer",
    mock_token_repository: "Mock",
    mock_oauth2_adapter: "Mock",
    cipher_usecase: CipherUsecase,
) -> None:
    """Test that handle marks tokens as invalid on OAuth2 API error."""
    handler = await token_update_handler_container.get(token_update_handler.TokenUpdateHandler[AsyncSession])
    token_repository = mock_token_repository
    hh_oauth2_adapter = mock_oauth2_adapter

    user_id = "user123"
    old_refresh_token = "old_refresh_token"

    payload = TokenUpdatePayload(user_id=user_id)
    task = OutboxTask(
        id=TaskID.from_uuid(uuid4()),
        task_type=OutboxTaskType.TOKEN_UPDATE,
        payload=payload.model_dump(mode="json"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        available_at=datetime.now(UTC),
        attempts=0,
        status=OutboxTaskStatus.PENDING,
    )

    session = Mock()
    ctx = OutboxContext[AsyncSession](session=session)

    encrypt_old_refresh_response = cipher_usecase.encrypt_bytes(
        CipherUsecase.EncryptBytesRequest(data=old_refresh_token.encode("utf-8"))
    )

    old_token_pair = TokenPair(
        user_id=user_id,
        encrypted_access_token=b"old_encrypted_access",
        encrypted_refresh_token=encrypt_old_refresh_response.data,
        expires_at=datetime.now(UTC),
        token_type="bearer",
        is_invalid=False,
    )

    token_repository.lock_tokens_for_update = AsyncMock(return_value=old_token_pair)
    hh_oauth2_adapter.refresh_tokens = AsyncMock(side_effect=oauth2_protocol.OAuth2APIError("API error"))

    def _mark_invalid(
        _session: Mock, request: token_protocol.HeadHunterTokenRepositoryProtocol.MarkTokensInvalidRequest
    ) -> TokenPair:
        return TokenPair(
            user_id=request.user_id,
            encrypted_access_token=b"encrypted",
            encrypted_refresh_token=b"encrypted",
            expires_at=datetime.now(UTC),
            token_type="bearer",
            is_invalid=True,
        )

    token_repository.mark_tokens_invalid = AsyncMock(side_effect=_mark_invalid)

    # Mock context() as async context manager
    separate_session = Mock()

    @asynccontextmanager
    async def _context():
        yield separate_session

    token_repository.context = _context

    with pytest.raises(token_update_handler.TokenUpdateHandlerAPIError):
        await handler.handle(ctx=ctx, task=task)

    token_repository.mark_tokens_invalid.assert_awaited_once()  # pyright: ignore[reportAny]


@pytest.mark.asyncio
async def test_handle_fails_task_when_max_retries_exceeded(
    token_update_handler_container: "AsyncContainer",
    mock_token_repository: "Mock",
) -> None:
    """Test that handle marks task as failed when max retries is exceeded."""
    handler = await token_update_handler_container.get(token_update_handler.TokenUpdateHandler[AsyncSession])

    user_id = "user123"

    payload = TokenUpdatePayload(user_id=user_id)
    task_id = TaskID.from_uuid(uuid4())
    now = datetime.now(UTC)
    task_with_max_retries = OutboxTask(
        id=task_id,
        task_type=OutboxTaskType.TOKEN_UPDATE,
        payload=payload.model_dump(mode="json"),
        created_at=now,
        updated_at=now,
        available_at=now,
        attempts=99,
        status=OutboxTaskStatus.PENDING,
    )

    session = Mock()
    ctx = OutboxContext[AsyncSession](session=session)

    separate_session = Mock()

    @asynccontextmanager
    async def _outbox_context():
        yield separate_session

    token_repository = mock_token_repository
    token_repository.mark_tokens_invalid = AsyncMock()
    token_repository.lock_tokens_for_update = AsyncMock()
    mock_token_update_scheduler = cast("Mock", handler._token_update_scheduler)
    mock_refresh_tokens_usecase = cast("Mock", handler._refresh_tokens_usecase)

    mock_token_update_scheduler.schedule = AsyncMock()
    mock_refresh_tokens_usecase.refresh_and_update_tokens = AsyncMock()

    # Mock outbox_repo.context for _fail_task_on_max_retries
    handler_outbox_repo = cast("Mock", handler._outbox_repo)
    handler_outbox_repo.context = _outbox_context
    handler_outbox_repo.update_task = AsyncMock(return_value=task_with_max_retries)

    await handler.handle(ctx=ctx, task=task_with_max_retries)

    token_repository.mark_tokens_invalid.assert_not_called()  # pyright: ignore[reportAny]
    token_repository.lock_tokens_for_update.assert_not_called()  # pyright: ignore[reportAny]
    mock_token_update_scheduler.schedule.assert_not_called()  # pyright: ignore[reportAny]
    mock_refresh_tokens_usecase.refresh_and_update_tokens.assert_not_called()  # pyright: ignore[reportAny]
