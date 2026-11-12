from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.adapters.resume_search_scan.postgres.adapter import PostgresResumeSearchScanRepositoryAdapter
from hharon.infra.postgres import AsyncSessionFactory


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
def adapter(mock_session_factory: AsyncSessionFactory) -> PostgresResumeSearchScanRepositoryAdapter:
    """Create PostgresResumeSearchScanRepositoryAdapter for testing."""
    return PostgresResumeSearchScanRepositoryAdapter(session_factory=mock_session_factory)


@pytest.fixture
def session_with_nested_tx(mock_session: AsyncSession) -> AsyncSession:
    """Session with begin_nested() returning a no-op async context manager."""
    mock_session.begin_nested = Mock(return_value=_nested_tx_context())  # type: ignore[assignment]
    return mock_session


@pytest.fixture
def resume_id() -> str:
    return "resume_789"
