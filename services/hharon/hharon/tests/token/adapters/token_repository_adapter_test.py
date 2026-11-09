from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.adapters.postgres_models.models import HeadHunterTokenORM
from hharon.adapters.token.postgres.adapter import PostgresHeadHunterTokenRepositoryAdapter
from hharon.domain.token import TokenPair
from hharon.protocols.token.protocol import (
    HeadHunterTokenRepositoryNotFoundError,
    HeadHunterTokenRepositoryProtocol,
)


@pytest.mark.asyncio
async def test_save_tokens_creates_tokens_in_database(mock_session: AsyncSession) -> None:
    """Test that save_tokens creates tokens in the database."""
    user_id = "user123"
    encrypted_access_token = b"encrypted_access_token"
    encrypted_refresh_token = b"encrypted_refresh_token"
    expires_at = datetime.now(UTC)
    token_type = "bearer"

    orm_model = HeadHunterTokenORM(
        id=uuid4(),
        user_id=user_id,
        encrypted_access_token=encrypted_access_token,
        encrypted_refresh_token=encrypted_refresh_token,
        expires_at=expires_at,
        token_type=token_type,
    )
    orm_model.to_domain = Mock(  # type: ignore[assignment]
        return_value=TokenPair(
            user_id=user_id,
            encrypted_access_token=encrypted_access_token,
            encrypted_refresh_token=encrypted_refresh_token,
            expires_at=expires_at,
            token_type=token_type,
        )
    )

    mock_session.add = Mock()  # type: ignore[assignment]
    mock_session.flush = AsyncMock()  # type: ignore[assignment]

    def _add(model: HeadHunterTokenORM) -> None:
        assert model.encrypted_access_token == encrypted_access_token
        assert model.encrypted_refresh_token == encrypted_refresh_token
        assert model.expires_at == expires_at
        assert model.token_type == token_type
        model.id = orm_model.id
        model.to_domain = orm_model.to_domain  # type: ignore[assignment]

    mock_session.add.side_effect = _add  # type: ignore[attr-defined]

    session_factory = Mock(return_value=mock_session)
    adapter = PostgresHeadHunterTokenRepositoryAdapter(session_factory=session_factory)

    async with adapter.context() as session:
        result = await adapter.save_tokens(
            session,
            HeadHunterTokenRepositoryProtocol.SaveTokensRequest(
                user_id=user_id,
                encrypted_access_token=encrypted_access_token,
                encrypted_refresh_token=encrypted_refresh_token,
                expires_at=expires_at,
                token_type=token_type,
            ),
        )

    assert isinstance(result, TokenPair)
    assert result.encrypted_access_token == encrypted_access_token
    assert result.encrypted_refresh_token == encrypted_refresh_token
    assert result.token_type == token_type
    mock_session.add.assert_called_once()  # type: ignore[attr-defined]
    mock_session.flush.assert_awaited_once()  # type: ignore[attr-defined]
    mock_session.commit.assert_awaited_once()  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.asyncio
async def test_get_tokens_returns_tokens_when_found(
    mock_session: AsyncSession, mock_token_orm_model: HeadHunterTokenORM
) -> None:
    """Test that get_tokens returns tokens when found in database."""
    orm_model = mock_token_orm_model

    # Mock SQLAlchemy result
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=orm_model)
    mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[assignment]

    session_factory = Mock(return_value=mock_session)
    adapter = PostgresHeadHunterTokenRepositoryAdapter(session_factory=session_factory)

    async with adapter.context() as session:
        result = await adapter.get_tokens(
            session, HeadHunterTokenRepositoryProtocol.GetTokensRequest(user_id=orm_model.user_id)
        )

    assert result is not None
    assert isinstance(result, TokenPair)
    assert result.user_id == orm_model.user_id
    mock_session.execute.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_get_tokens_returns_none_when_not_found(mock_session: AsyncSession) -> None:
    """Test that get_tokens returns None when tokens are not found."""
    user_id = "user123"

    # Mock SQLAlchemy result
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[assignment]

    session_factory = Mock(return_value=mock_session)
    adapter = PostgresHeadHunterTokenRepositoryAdapter(session_factory=session_factory)

    async with adapter.context() as session:
        result = await adapter.get_tokens(session, HeadHunterTokenRepositoryProtocol.GetTokensRequest(user_id=user_id))

    assert result is None
    mock_session.execute.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_lock_tokens_for_update_returns_tokens_when_found(
    mock_session: AsyncSession, mock_token_orm_model: HeadHunterTokenORM
) -> None:
    """Test that lock_tokens_for_update returns tokens when found in database."""

    orm_model = mock_token_orm_model

    # Mock SQLAlchemy result
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=orm_model)
    mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[assignment]

    session_factory = Mock(return_value=mock_session)
    adapter = PostgresHeadHunterTokenRepositoryAdapter(session_factory=session_factory)

    async with adapter.context() as session:
        result = await adapter.lock_tokens_for_update(
            session, HeadHunterTokenRepositoryProtocol.LockTokensRequest(user_id=orm_model.user_id)
        )

    assert result is not None
    assert isinstance(result, TokenPair)
    assert result.user_id == orm_model.user_id
    mock_session.execute.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_lock_tokens_for_update_returns_none_when_not_found(mock_session: AsyncSession) -> None:
    """Test that lock_tokens_for_update returns None when tokens are not found."""
    user_id = "user123"

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[assignment]

    session_factory = Mock(return_value=mock_session)
    adapter = PostgresHeadHunterTokenRepositoryAdapter(session_factory=session_factory)

    async with adapter.context() as session:
        result = await adapter.lock_tokens_for_update(
            session, HeadHunterTokenRepositoryProtocol.LockTokensRequest(user_id=user_id)
        )

    assert result is None
    mock_session.execute.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_update_tokens_updates_tokens_in_database(mock_session: AsyncSession) -> None:
    """Test that update_tokens updates tokens in the database."""
    user_id = "user123"
    new_encrypted_access_token = b"new_encrypted_access_token"
    new_encrypted_refresh_token = b"new_encrypted_refresh_token"
    new_expires_at = datetime.now(UTC)
    new_token_type = "bearer"

    orm_model = HeadHunterTokenORM(
        id=uuid4(),
        user_id=user_id,
        encrypted_access_token=b"old_encrypted_access_token",
        encrypted_refresh_token=b"old_encrypted_refresh_token",
        expires_at=datetime.now(UTC),
        token_type="bearer",
    )
    orm_model.to_domain = Mock(  # type: ignore[assignment]
        return_value=TokenPair(
            user_id=user_id,
            encrypted_access_token=new_encrypted_access_token,
            encrypted_refresh_token=new_encrypted_refresh_token,
            expires_at=new_expires_at,
            token_type=new_token_type,
        )
    )

    # Mock SQLAlchemy result
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=orm_model)
    mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[assignment]
    mock_session.flush = AsyncMock()  # type: ignore[assignment]

    session_factory = Mock(return_value=mock_session)
    adapter = PostgresHeadHunterTokenRepositoryAdapter(session_factory=session_factory)

    async with adapter.context() as session:
        result = await adapter.update_tokens(
            session,
            HeadHunterTokenRepositoryProtocol.UpdateTokensRequest(
                user_id=user_id,
                encrypted_access_token=new_encrypted_access_token,
                encrypted_refresh_token=new_encrypted_refresh_token,
                expires_at=new_expires_at,
                token_type=new_token_type,
            ),
        )

    assert isinstance(result, TokenPair)
    assert result.user_id == user_id
    assert orm_model.encrypted_access_token == new_encrypted_access_token
    assert orm_model.encrypted_refresh_token == new_encrypted_refresh_token
    assert orm_model.token_type == new_token_type
    mock_session.flush.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_update_tokens_raises_error_when_not_found(mock_session: AsyncSession) -> None:
    """Test that update_tokens raises error when tokens are not found."""
    user_id = "user123"

    # Mock SQLAlchemy result
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[assignment]

    session_factory = Mock(return_value=mock_session)
    adapter = PostgresHeadHunterTokenRepositoryAdapter(session_factory=session_factory)

    async with adapter.context() as session:
        with pytest.raises(HeadHunterTokenRepositoryNotFoundError):
            _ = await adapter.update_tokens(
                session,
                HeadHunterTokenRepositoryProtocol.UpdateTokensRequest(
                    user_id=user_id,
                    encrypted_access_token=b"token",
                    encrypted_refresh_token=b"refresh",
                    expires_at=datetime.now(UTC),
                    token_type="bearer",
                ),
            )


@pytest.mark.asyncio
async def test_mark_tokens_invalid_marks_tokens_as_invalid(mock_session: AsyncSession) -> None:
    """Test that mark_tokens_invalid marks tokens as invalid."""
    user_id = "user123"

    # Mock ORM model
    orm_model = HeadHunterTokenORM(
        id=uuid4(),
        user_id=user_id,
        encrypted_access_token=b"encrypted_access_token",
        encrypted_refresh_token=b"encrypted_refresh_token",
        expires_at=datetime.now(UTC),
        token_type="bearer",
        is_invalid=False,
    )
    orm_model.to_domain = Mock(  # type: ignore[assignment]
        return_value=TokenPair(
            user_id=user_id,
            encrypted_access_token=b"encrypted_access_token",
            encrypted_refresh_token=b"encrypted_refresh_token",
            expires_at=datetime.now(UTC),
            token_type="bearer",
            is_invalid=True,
        )
    )

    # Mock SQLAlchemy result
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=orm_model)
    mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[assignment]
    mock_session.flush = AsyncMock()  # type: ignore[assignment]

    session_factory = Mock(return_value=mock_session)
    adapter = PostgresHeadHunterTokenRepositoryAdapter(session_factory=session_factory)

    async with adapter.context() as session:
        result = await adapter.mark_tokens_invalid(
            session, HeadHunterTokenRepositoryProtocol.MarkTokensInvalidRequest(user_id=user_id)
        )

    assert isinstance(result, TokenPair)
    assert orm_model.is_invalid is True
    assert result.is_invalid is True
    mock_session.flush.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_mark_tokens_invalid_raises_error_when_not_found(mock_session: AsyncSession) -> None:
    """Test that mark_tokens_invalid raises error when tokens are not found."""
    user_id = "user123"

    # Mock SQLAlchemy result
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[assignment]

    session_factory = Mock(return_value=mock_session)
    adapter = PostgresHeadHunterTokenRepositoryAdapter(session_factory=session_factory)

    async with adapter.context() as session:
        with pytest.raises(HeadHunterTokenRepositoryNotFoundError):
            _ = await adapter.mark_tokens_invalid(
                session, HeadHunterTokenRepositoryProtocol.MarkTokensInvalidRequest(user_id=user_id)
            )
