from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.adapters.postgres_models.models import HharonUserORM
from hharon.adapters.user.postgres.adapter import PostgresHharonUserRepositoryAdapter
from hharon.domain.user import HharonUser
from hharon.protocols.user.protocol import HharonUserRepositoryProtocol


@pytest.mark.asyncio
async def test_create_user_creates_user_in_database(mock_session: AsyncSession) -> None:
    """Test that create_user creates a user in the database."""
    user_id = "user_123"
    hh_manager_id = "hh_123"
    name = "John Doe"
    email = "john@example.com"
    hh_employer_id = "employer_123"

    # Mock ORM model
    orm_model = HharonUserORM(
        id=uuid4(),
        user_id=user_id,
        hh_manager_id=hh_manager_id,
        hh_employer_id=hh_employer_id,
        name=name,
        email=email,
    )
    orm_model.to_domain = Mock(  # type: ignore[assignment]
        return_value=HharonUser(
            user_id=user_id,
            hh_manager_id=hh_manager_id,
            hh_employer_id=hh_employer_id,
            name=name,
            email=email,
        )
    )

    # Mock session methods
    mock_session.add = Mock()  # type: ignore[assignment]
    mock_session.flush = AsyncMock()  # type: ignore[assignment]

    # Create a mock that will be added to session
    def _add(model: HharonUserORM) -> None:
        assert model.user_id == user_id
        assert model.hh_manager_id == hh_manager_id
        assert model.name == name
        assert model.email == email
        assert model.hh_employer_id == hh_employer_id
        # Simulate setting the id after flush
        model.id = orm_model.id

    mock_session.add.side_effect = _add  # type: ignore[attr-defined]

    session_factory = Mock(return_value=mock_session)
    adapter = PostgresHharonUserRepositoryAdapter(session_factory=session_factory)

    async with adapter.context() as session:
        result = await adapter.create_user(
            session,
            HharonUserRepositoryProtocol.CreateUserRequest(
                user_id=user_id,
                hh_manager_id=hh_manager_id,
                name=name,
                email=email,
                hh_employer_id=hh_employer_id,
            ),
        )

    assert isinstance(result, HharonUser)
    assert result.user_id == user_id
    assert result.hh_manager_id == hh_manager_id
    assert result.name == name
    assert result.email == email
    assert result.hh_employer_id == hh_employer_id
    mock_session.add.assert_called_once()  # type: ignore[attr-defined]
    mock_session.flush.assert_awaited_once()  # type: ignore[attr-defined]
    mock_session.commit.assert_awaited_once()  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.asyncio
async def test_get_user_returns_user_when_found(mock_session: AsyncSession, mock_orm_model: HharonUserORM) -> None:
    """Test that get_user returns user when found in database."""
    user_id = "user123"
    orm_model = mock_orm_model

    # Mock SQLAlchemy result
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=orm_model)
    mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[assignment]

    session_factory = Mock(return_value=mock_session)
    adapter = PostgresHharonUserRepositoryAdapter(session_factory=session_factory)

    async with adapter.context() as session:
        result = await adapter.get_user(session, HharonUserRepositoryProtocol.GetUserRequest(user_id=user_id))

    assert result is not None
    assert isinstance(result, HharonUser)
    assert result.user_id == mock_orm_model.user_id
    mock_session.execute.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_get_user_returns_none_when_not_found(mock_session: AsyncSession) -> None:
    """Test that get_user returns None when user is not found."""
    user_id = "user1234"

    # Mock SQLAlchemy result
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[assignment]

    session_factory = Mock(return_value=mock_session)
    adapter = PostgresHharonUserRepositoryAdapter(session_factory=session_factory)

    async with adapter.context() as session:
        result = await adapter.get_user(session, HharonUserRepositoryProtocol.GetUserRequest(user_id=user_id))

    assert result is None
    mock_session.execute.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_get_user_by_hh_maneger_id_returns_user_when_found(
    mock_session: AsyncSession, mock_orm_model: HharonUserORM
) -> None:
    """Test that get_user_by_hh_manager_id returns user when found in database."""
    hh_manager_id = mock_orm_model.hh_manager_id
    orm_model = mock_orm_model

    # Mock SQLAlchemy result
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=orm_model)
    mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[assignment]

    session_factory = Mock(return_value=mock_session)
    adapter = PostgresHharonUserRepositoryAdapter(session_factory=session_factory)

    async with adapter.context() as session:
        result = await adapter.get_user_by_hh_manager_id(
            session, HharonUserRepositoryProtocol.GetUserByHhIdRequest(hh_manager_id=hh_manager_id)
        )

    assert result is not None
    assert isinstance(result, HharonUser)
    assert result.hh_manager_id == mock_orm_model.hh_manager_id
    mock_session.execute.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_update_user_updates_user_in_database(mock_session: AsyncSession) -> None:
    """Test that update_user updates user in the database."""
    user_id = "user123"
    new_name = "Jane Doe"
    new_email = "jane@example.com"

    # Mock ORM model
    orm_model = HharonUserORM(
        user_id=user_id,
        hh_manager_id="hh_123",
        hh_employer_id="employer_123",
        name="John Doe",
        email="john@example.com",
    )
    orm_model.to_domain = Mock(  # type: ignore[assignment]
        return_value=HharonUser(
            user_id=user_id,
            hh_manager_id="hh_123",
            hh_employer_id="employer_123",
            name=new_name,
            email=new_email,
        )
    )

    # Mock SQLAlchemy result
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=orm_model)
    mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[assignment]
    mock_session.flush = AsyncMock()  # type: ignore[assignment]

    session_factory = Mock(return_value=mock_session)
    adapter = PostgresHharonUserRepositoryAdapter(session_factory=session_factory)

    async with adapter.context() as session:
        result = await adapter.update_user(
            session,
            HharonUserRepositoryProtocol.UpdateUserRequest(user_id=user_id, name=new_name, email=new_email),
        )

    assert isinstance(result, HharonUser)
    assert result.name == new_name
    assert result.email == new_email
    assert orm_model.name == new_name
    assert orm_model.email == new_email
    mock_session.flush.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_update_user_raises_error_when_user_not_found(mock_session: AsyncSession) -> None:
    """Test that update_user raises error when user is not found."""
    user_id = "user_123"

    # Mock SQLAlchemy result
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[assignment]

    session_factory = Mock(return_value=mock_session)
    adapter = PostgresHharonUserRepositoryAdapter(session_factory=session_factory)

    async with adapter.context() as session:
        with pytest.raises(ValueError, match="User not found"):
            _ = await adapter.update_user(
                session,
                HharonUserRepositoryProtocol.UpdateUserRequest(user_id=user_id, name="New Name"),
            )
