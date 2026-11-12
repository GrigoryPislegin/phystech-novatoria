"""Integration tests for PostgresResumeSearchScanRepositoryAdapter."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.adapters.postgres_models.models import SearchCampaignORM
from hharon.adapters.resume_search_scan.postgres.adapter import PostgresResumeSearchScanRepositoryAdapter
from hharon.domain.known_candidate import KnownCandidateSourceEnum
from hharon.domain.resume_search_scan import ProcessedScanCandidate
from hharon.domain.scalars import SearchCampaignID
from hharon.domain.search_campaign import SearchCampaign, SearchCampaignStatus
from hharon.infra.postgres import AsyncSessionFactory
from hharon.protocols.resume_search_scan import protocol


@pytest.fixture
def captured_statement() -> list:
    """Capture the statement passed to session.execute."""
    return []


@pytest.fixture
def mock_session_with_capture(captured_statement: list) -> AsyncSession:
    """Create a mock session that captures execute argument."""

    async def _execute(statement: object) -> Mock:
        captured_statement.append(statement)
        result = Mock()
        result.scalar_one_or_none = Mock(return_value=None)
        result.scalar = Mock(return_value=0)
        return result

    session = Mock(spec=AsyncSession)
    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock(return_value=None)
    session.rollback = AsyncMock(return_value=None)
    session.close = AsyncMock(return_value=None)
    return session


@pytest.fixture
def adapter_with_capture(mock_session_with_capture: AsyncSession) -> PostgresResumeSearchScanRepositoryAdapter:
    """Create adapter with session that captures execute calls."""
    factory = Mock(spec=AsyncSessionFactory)
    factory.return_value = mock_session_with_capture
    return PostgresResumeSearchScanRepositoryAdapter(session_factory=factory)


@pytest.mark.asyncio
async def test_get_campaign_by_vacancy_query_orders_active_first_then_created_at_desc(
    adapter_with_capture: PostgresResumeSearchScanRepositoryAdapter,
    captured_statement: list,
) -> None:
    """Verify get_campaign_by_vacancy builds query with correct ORDER BY: active first, then by created_at desc."""
    vacancy_id = "vacancy_123"
    request = protocol.ResumeSearchScanRepositoryProtocol.GetCampaignByVacancyRequest(vacancy_id=vacancy_id)

    async with adapter_with_capture.context() as session:
        await adapter_with_capture.get_campaign_by_vacancy(session, request)

    assert len(captured_statement) == 1
    stmt = captured_statement[0]
    compiled = stmt.compile(dialect=dialect(), compile_kwargs={"literal_binds": True})
    sql = str(compiled)

    assert "ORDER BY" in sql
    assert "ACTIVE" in sql
    assert "created_at DESC" in sql
    assert "LIMIT 1" in sql
    assert "vacancy_id" in sql
    assert "deleted_at IS NULL" in sql


@pytest.mark.asyncio
async def test_get_campaign_by_vacancy_returns_campaign_when_found(
    adapter: PostgresResumeSearchScanRepositoryAdapter,
    mock_session: AsyncSession,
) -> None:
    """Verify get_campaign_by_vacancy returns domain model when campaign exists."""
    vacancy_id = "vacancy_123"
    campaign_id = uuid4()
    orm_model = SearchCampaignORM(
        id=campaign_id,
        user_id="user_123",
        vacancy_id=vacancy_id,
        status=SearchCampaignStatus.ACTIVE,
        active_until=datetime.now(UTC) + timedelta(days=1),
        daily_limit=30,
        search_params=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    result_mock = Mock()
    result_mock.scalar_one_or_none = Mock(return_value=orm_model)
    mock_session.execute = AsyncMock(return_value=result_mock)  # type: ignore[assignment]

    request = protocol.ResumeSearchScanRepositoryProtocol.GetCampaignByVacancyRequest(vacancy_id=vacancy_id)

    async with adapter.context() as session:
        result = await adapter.get_campaign_by_vacancy(session, request)

    assert result is not None
    assert isinstance(result, SearchCampaign)
    assert result.vacancy_id == vacancy_id
    assert result.status == SearchCampaignStatus.ACTIVE
    assert result.id == SearchCampaignID.from_uuid(campaign_id)


@pytest.mark.asyncio
async def test_get_campaign_by_vacancy_returns_none_when_not_found(
    adapter: PostgresResumeSearchScanRepositoryAdapter,
    mock_session: AsyncSession,
) -> None:
    """Verify get_campaign_by_vacancy returns None when no campaign exists for vacancy."""
    result_mock = Mock()
    result_mock.scalar_one_or_none = Mock(return_value=None)
    mock_session.execute = AsyncMock(return_value=result_mock)  # type: ignore[assignment]

    request = protocol.ResumeSearchScanRepositoryProtocol.GetCampaignByVacancyRequest(vacancy_id="vacancy_nonexistent")

    async with adapter.context() as session:
        result = await adapter.get_campaign_by_vacancy(session, request)

    assert result is None


@pytest.mark.asyncio
async def test_mark_candidate_processed_inserts_known_candidate_and_returns_domain(
    adapter: PostgresResumeSearchScanRepositoryAdapter,
    session_with_nested_tx: AsyncSession,
    resume_id: str,
) -> None:
    """mark_candidate_processed does INSERT...SELECT from SearchCampaign with on_conflict_do_nothing,
    returns ProcessedScanCandidate."""
    vacancy_id = "vacancy_123"

    # Insert with on_conflict_do_nothing
    insert_result_mock = Mock()
    insert_result_mock.scalar_one_or_none = Mock(return_value="1a2b3c")

    session_with_nested_tx.execute = AsyncMock(return_value=insert_result_mock)  # type: ignore[assignment]

    campaign_id = SearchCampaignID()
    result = await adapter.mark_candidate_processed(
        session_with_nested_tx,
        protocol.ResumeSearchScanRepositoryProtocol.MarkCandidateProcessedRequest(
            resume_id=resume_id,
            vacancy_id=vacancy_id,
            source=KnownCandidateSourceEnum.SEARCH_CAMPAIGN,
            source_id=campaign_id,
        ),
    )

    assert result is not None
    assert isinstance(result, ProcessedScanCandidate)
    assert result.resume_id == resume_id
    assert result.vacancy_id == vacancy_id
    assert session_with_nested_tx.execute.call_count == 1  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_mark_candidate_processed_returns_none_on_duplicate(
    adapter: PostgresResumeSearchScanRepositoryAdapter,
    session_with_nested_tx: AsyncSession,
    resume_id: str,
) -> None:
    """mark_candidate_processed returns None when (resume_id, vacancy_id) already exists (on_conflict_do_nothing)."""
    vacancy_id = "vacancy_123"

    # Insert with on_conflict_do_nothing returns rowcount=0 for duplicate
    insert_result_mock = Mock()
    insert_result_mock.scalar_one_or_none = Mock(return_value=None)

    session_with_nested_tx.execute = AsyncMock(return_value=insert_result_mock)  # type: ignore[assignment]

    campaign_id = SearchCampaignID()
    result = await adapter.mark_candidate_processed(
        session_with_nested_tx,
        protocol.ResumeSearchScanRepositoryProtocol.MarkCandidateProcessedRequest(
            resume_id=resume_id,
            vacancy_id=vacancy_id,
            source=KnownCandidateSourceEnum.SEARCH_CAMPAIGN,
            source_id=campaign_id,
        ),
    )

    assert result is None
    assert session_with_nested_tx.execute.call_count == 1  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_count_collected_by_date_filters_by_source_and_campaign_id(
    adapter_with_capture: PostgresResumeSearchScanRepositoryAdapter,
    captured_statement: list,
) -> None:
    """count_collected_by_date filters by source=hh_search_campaign and source_id=campaign_id."""
    campaign_id = SearchCampaignID()
    request_date = date(2026, 2, 20)
    request = protocol.ResumeSearchScanRepositoryProtocol.CountCollectedTodayRequest(
        campaign_id=campaign_id,
        date=request_date,
    )

    async with adapter_with_capture.context() as session:
        await adapter_with_capture.count_collected_by_date(session, request)

    assert len(captured_statement) >= 1
    count_stmt = captured_statement[-1]
    compiled = count_stmt.compile(dialect=dialect(), compile_kwargs={"literal_binds": True})
    sql = str(compiled)

    assert "known_candidates" in sql
    assert "search_campaign" in sql
    assert "source_id" in sql
