from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.adapters.postgres_models.models import KnownCandidateORM, ResponseCollectionSettingsORM
from hharon.adapters.response_collection.postgres.adapter import PostgresResponseCollectionRepositoryAdapter
from hharon.domain.response_collection import ResponseCollectionSettings, ResponseCollectionStatus
from hharon.domain.scalars import ResponseCollectionSettingsID
from hharon.infra.postgres import AsyncSessionFactory


def _uid(prefix: str = "") -> str:
    """Short unique id for test data."""
    return f"{prefix}{uuid4().hex[:12]}" if prefix else uuid4().hex[:12]


@pytest.fixture
def vacancy_id() -> str:
    return _uid("vacancy_")


@pytest.fixture
def headhunter_vacancy_id() -> str:
    return _uid("hh_vacancy_")


@pytest.fixture
def resume_id() -> str:
    return _uid("resume_")


@pytest.fixture
def headhunter_collections() -> list[str]:
    return [_uid("col_"), _uid("col_")]


@asynccontextmanager
async def _nested_tx_context() -> AsyncGenerator[None]:
    """Async context manager for session.begin_nested() mock."""
    yield


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
def adapter(mock_session_factory: AsyncSessionFactory) -> PostgresResponseCollectionRepositoryAdapter:
    """Create PostgresResponseCollectionRepositoryAdapter for testing."""
    return PostgresResponseCollectionRepositoryAdapter(session_factory=mock_session_factory)


@pytest.fixture
def mock_settings_orm(
    vacancy_id: str,
    headhunter_vacancy_id: str,
    headhunter_collections: list[str],
) -> ResponseCollectionSettingsORM:
    """Create a mock ResponseCollectionSettingsORM with generated test data."""
    settings_id = ResponseCollectionSettingsID()

    orm_model = ResponseCollectionSettingsORM(
        id=settings_id,
        vacancy_id=vacancy_id,
        headhunter_vacancy_id=headhunter_vacancy_id,
        headhunter_collections=headhunter_collections,
        user_id="user_123",
        status=ResponseCollectionStatus.ACTIVE,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    orm_model.to_domain = Mock(  # type: ignore[assignment]
        return_value=ResponseCollectionSettings(
            id=settings_id,
            vacancy_id=vacancy_id,
            headhunter_vacancy_id=headhunter_vacancy_id,
            headhunter_collections=headhunter_collections,
            user_id="user_123",
            status=ResponseCollectionStatus.ACTIVE,
        )
    )
    return orm_model


@pytest.fixture
def mock_known_candidate_orm(
    resume_id: str,
    vacancy_id: str,
) -> KnownCandidateORM:
    """Create a mock KnownCandidateORM with generated test data (response collection case)."""
    return KnownCandidateORM(
        id=uuid4(),
        resume_id=resume_id,
        vacancy_id=vacancy_id,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def session_with_nested_tx(mock_session: AsyncSession) -> AsyncSession:
    """Session with begin_nested() returning a no-op async context manager."""
    mock_session.begin_nested = Mock(return_value=_nested_tx_context())  # type: ignore[assignment]
    return mock_session
