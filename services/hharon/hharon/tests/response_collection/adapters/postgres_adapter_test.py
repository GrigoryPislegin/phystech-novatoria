from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.adapters.postgres_models.models import ResponseCollectionSettingsORM
from hharon.adapters.response_collection.postgres.adapter import PostgresResponseCollectionRepositoryAdapter
from hharon.domain.known_candidate import KnownCandidateSourceEnum
from hharon.domain.response_collection import ProcessedCandidate, ResponseCollectionSettings, ResponseCollectionStatus
from hharon.domain.scalars import ResponseCollectionSettingsID
from hharon.protocols.response_collection import ResponseCollectionRepositoryProtocol


@pytest.mark.asyncio
async def test_create_settings_persists_and_returns_domain(
    adapter: PostgresResponseCollectionRepositoryAdapter,
    mock_session: AsyncSession,
    vacancy_id: str,
    headhunter_vacancy_id: str,
    headhunter_collections: list[str],
) -> None:
    """create_settings adds ORM model, flushes, returns domain settings."""
    user_id = "user_123"
    settings_id = ResponseCollectionSettingsID()
    orm_model = ResponseCollectionSettingsORM(
        id=settings_id,
        vacancy_id=vacancy_id,
        headhunter_vacancy_id=headhunter_vacancy_id,
        headhunter_collections=headhunter_collections,
        user_id=user_id,
        status=ResponseCollectionStatus.ACTIVE,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    orm_model.to_domain = Mock(  # type: ignore[assignment]
        return_value=ResponseCollectionSettings(
            id=settings_id,
            vacancy_id=vacancy_id,
            user_id=user_id,
            headhunter_vacancy_id=headhunter_vacancy_id,
            headhunter_collections=headhunter_collections,
            status=ResponseCollectionStatus.ACTIVE,
        )
    )

    def _add(model: ResponseCollectionSettingsORM) -> None:
        assert model.vacancy_id == vacancy_id
        assert model.headhunter_vacancy_id == headhunter_vacancy_id
        assert model.headhunter_collections == headhunter_collections
        assert model.user_id == user_id
        model.id = settings_id
        model.to_domain = orm_model.to_domain  # type: ignore[assignment]

    mock_session.add = Mock()  # type: ignore[assignment]
    mock_session.flush = AsyncMock()  # type: ignore[assignment]
    mock_session.add.side_effect = _add  # type: ignore[attr-defined]

    result = await adapter.create_settings(
        mock_session,
        ResponseCollectionRepositoryProtocol.CreateSettingsRequest(
            user_id=user_id,
            vacancy_id=vacancy_id,
            hh_vacancy_id=headhunter_vacancy_id,
            hh_collections=headhunter_collections,
        ),
    )

    assert isinstance(result, ResponseCollectionSettings)
    assert result.vacancy_id == vacancy_id
    assert result.headhunter_vacancy_id == headhunter_vacancy_id
    assert result.headhunter_collections == headhunter_collections
    mock_session.add.assert_called_once()  # type: ignore[attr-defined]
    mock_session.flush.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_get_settings_returns_domain_when_found(
    adapter: PostgresResponseCollectionRepositoryAdapter,
    mock_session: AsyncSession,
    mock_settings_orm: ResponseCollectionSettingsORM,
) -> None:
    """get_settings returns ResponseCollectionSettings when record exists."""
    settings_id = mock_settings_orm.id
    result_mock = Mock()
    result_mock.scalar_one_or_none = Mock(return_value=mock_settings_orm)
    mock_session.execute = AsyncMock(return_value=result_mock)  # type: ignore[assignment]

    result = await adapter.get_settings(
        mock_session,
        ResponseCollectionRepositoryProtocol.GetSettingsRequest(
            settings_id=ResponseCollectionSettingsID.from_uuid(settings_id)
        ),
    )

    assert result is not None
    assert isinstance(result, ResponseCollectionSettings)
    assert result.id == ResponseCollectionSettingsID.from_uuid(settings_id)
    mock_session.execute.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_get_settings_returns_none_when_not_found(
    adapter: PostgresResponseCollectionRepositoryAdapter,
    mock_session: AsyncSession,
) -> None:
    """get_settings returns None when no record for settings_id."""
    settings_id = ResponseCollectionSettingsID()
    result_mock = Mock()
    result_mock.scalar_one_or_none = Mock(return_value=None)
    mock_session.execute = AsyncMock(return_value=result_mock)  # type: ignore[assignment]

    result = await adapter.get_settings(
        mock_session,
        ResponseCollectionRepositoryProtocol.GetSettingsRequest(settings_id=settings_id),
    )

    assert result is None
    mock_session.execute.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_get_settings_by_vacancy_returns_domain_when_found(
    adapter: PostgresResponseCollectionRepositoryAdapter,
    mock_session: AsyncSession,
    mock_settings_orm: ResponseCollectionSettingsORM,
    vacancy_id: str,
) -> None:
    """get_settings_by_vacancy returns settings by vacancy_id."""
    result_mock = Mock()
    result_mock.scalar_one_or_none = Mock(return_value=mock_settings_orm)
    mock_session.execute = AsyncMock(return_value=result_mock)  # type: ignore[assignment]

    result = await adapter.get_settings_by_vacancy(
        mock_session,
        ResponseCollectionRepositoryProtocol.GetSettingsByVacancyRequest(vacancy_id=vacancy_id),
    )

    assert result is not None
    assert isinstance(result, ResponseCollectionSettings)
    assert result.vacancy_id == vacancy_id
    mock_session.execute.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_mark_candidate_processed_inserts_known_candidate_and_returns_domain(
    adapter: PostgresResponseCollectionRepositoryAdapter,
    session_with_nested_tx: AsyncSession,
    resume_id: str,
) -> None:
    """mark_candidate_processed does INSERT...SELECT from settings, returns ProcessedCandidate."""
    vacancy_id = "vacancy_123"
    settings_id = ResponseCollectionSettingsID()

    result_mock = Mock()
    result_mock.scalar_one_or_none = Mock(return_value="1a2b3c")
    session_with_nested_tx.execute = AsyncMock(return_value=result_mock)  # type: ignore[assignment]

    result = await adapter.mark_candidate_processed(
        session_with_nested_tx,
        ResponseCollectionRepositoryProtocol.MarkCandidateProcessedRequest(
            resume_id=resume_id,
            vacancy_id=vacancy_id,
            source=KnownCandidateSourceEnum.RESPONSE_COLLECTION,
            source_id=settings_id,
        ),
    )

    assert result is not None
    assert isinstance(result, ProcessedCandidate)
    assert result.resume_id == resume_id
    assert result.vacancy_id == vacancy_id
    session_with_nested_tx.execute.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_mark_candidate_processed_returns_none_on_duplicate(
    adapter: PostgresResponseCollectionRepositoryAdapter,
    session_with_nested_tx: AsyncSession,
    resume_id: str,
) -> None:
    """mark_candidate_processed returns None when (resume_id, vacancy_id) already exists."""
    vacancy_id = "vacancy_123"
    settings_id = ResponseCollectionSettingsID()

    result_mock = Mock()
    result_mock.scalar_one_or_none = Mock(return_value=None)
    session_with_nested_tx.execute = AsyncMock(return_value=result_mock)  # type: ignore[assignment]

    result = await adapter.mark_candidate_processed(
        session_with_nested_tx,
        ResponseCollectionRepositoryProtocol.MarkCandidateProcessedRequest(
            resume_id=resume_id,
            vacancy_id=vacancy_id,
            source=KnownCandidateSourceEnum.RESPONSE_COLLECTION,
            source_id=settings_id,
        ),
    )

    assert result is None
    session_with_nested_tx.execute.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
@pytest.mark.parametrize("exists_result", [True, False])
async def test_is_candidate_processed_returns_exists_result(
    adapter: PostgresResponseCollectionRepositoryAdapter,
    mock_session: AsyncSession,
    resume_id: str,
    exists_result: bool,
) -> None:
    """is_candidate_processed returns True when record exists, False otherwise."""
    settings_id = ResponseCollectionSettingsID()
    mock_session.scalar = AsyncMock(return_value=exists_result)  # type: ignore[assignment]

    result = await adapter.is_candidate_processed(
        mock_session,
        ResponseCollectionRepositoryProtocol.IsCandidateProcessedRequest(
            resume_id=resume_id,
            settings_id=settings_id,
        ),
    )

    assert result is exists_result
    mock_session.scalar.assert_awaited_once()  # type: ignore[attr-defined]
