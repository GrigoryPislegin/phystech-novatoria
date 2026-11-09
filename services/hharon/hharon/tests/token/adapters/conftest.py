from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.adapters.postgres_models.models import HeadHunterTokenORM
from hharon.adapters.token.postgres.adapter import PostgresHeadHunterTokenRepositoryAdapter
from hharon.domain.token import TokenPair
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
def adapter(mock_session_factory: AsyncSessionFactory) -> PostgresHeadHunterTokenRepositoryAdapter:
    """Create PostgresHeadHunterTokenRepositoryAdapter for testing."""
    return PostgresHeadHunterTokenRepositoryAdapter(session_factory=mock_session_factory)


@pytest.fixture
def mock_token_orm_model() -> HeadHunterTokenORM:
    """Create a mock ORM model with default test data."""
    user_id = "user123"
    encrypted_access_token = b"encrypted_access_token"
    encrypted_refresh_token = b"encrypted_refresh_token"
    expires_at = datetime.now(UTC)
    token_type = "bearer"  # noqa: S105

    orm_model = HeadHunterTokenORM(
        id=uuid4(),
        user_id=user_id,
        encrypted_access_token=encrypted_access_token,
        encrypted_refresh_token=encrypted_refresh_token,
        expires_at=expires_at,
        token_type=token_type,
        is_invalid=False,
    )
    orm_model.to_domain = Mock(  # type: ignore[assignment]
        return_value=TokenPair(
            user_id=user_id,
            encrypted_access_token=encrypted_access_token,
            encrypted_refresh_token=encrypted_refresh_token,
            expires_at=expires_at,
            token_type=token_type,
            is_invalid=False,
        )
    )
    return orm_model
