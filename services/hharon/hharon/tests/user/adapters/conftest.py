from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.adapters.postgres_models.models import HharonUserORM
from hharon.adapters.user.postgres.adapter import PostgresHharonUserRepositoryAdapter
from hharon.domain.user import HharonUser
from hharon.infra.postgres import AsyncSessionFactory


@pytest.fixture
def mock_session() -> AsyncSession:
    """Create a mock AsyncSession."""
    session = Mock(spec=AsyncSession)
    session.commit = AsyncMock(return_value=None)
    session.rollback = AsyncMock(return_value=None)
    session.close = AsyncMock(return_value=None)
    return session


@pytest.fixture
def mock_session_factory(mock_session: AsyncSession) -> AsyncSessionFactory:
    """Create a mock AsyncSessionFactory."""
    factory = Mock(spec=AsyncSessionFactory)
    factory.return_value = mock_session
    return factory


@pytest.fixture
def adapter(mock_session_factory: AsyncSessionFactory) -> PostgresHharonUserRepositoryAdapter:
    """Create PostgresHharonUserRepositoryAdapter for testing."""
    return PostgresHharonUserRepositoryAdapter(session_factory=mock_session_factory)


@pytest.fixture
def mock_orm_model() -> HharonUserORM:
    """Create a mock ORM model with default test data."""
    user_id = "user_123"
    hh_manager_id = "hh_123"
    hh_employer_id = "654321"
    name = "John Doe"
    email = "john@example.com"

    orm_model = HharonUserORM(
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
    return orm_model
