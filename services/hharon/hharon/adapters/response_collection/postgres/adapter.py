from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import final, override

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.adapters.postgres_models.models import KnownCandidateORM, ResponseCollectionSettingsORM
from hharon.domain.response_collection import ProcessedCandidate, ResponseCollectionSettings, ResponseCollectionStatus
from hharon.infra.postgres import AsyncSessionFactory
from hharon.protocols.response_collection.db_protocol import ResponseCollectionRepositoryProtocol


@final
class PostgresResponseCollectionRepositoryAdapter(ResponseCollectionRepositoryProtocol[AsyncSession]):
    def __init__(self, session_factory: AsyncSessionFactory) -> None:
        self._session_factory = session_factory

    @override
    @asynccontextmanager
    async def context(self) -> AsyncGenerator[AsyncSession]:
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @override
    async def create_settings(
        self, session: AsyncSession, request: ResponseCollectionRepositoryProtocol.CreateSettingsRequest
    ) -> ResponseCollectionSettings:
        model = ResponseCollectionSettingsORM(
            vacancy_id=request.vacancy_id,
            headhunter_vacancy_id=request.hh_vacancy_id,
            headhunter_collections=request.hh_collections,
            user_id=request.user_id,
            status=ResponseCollectionStatus.ACTIVE,
        )
        session.add(model)
        await session.flush()
        return model.to_domain()

    @override
    async def get_settings(
        self, session: AsyncSession, request: ResponseCollectionRepositoryProtocol.GetSettingsRequest
    ) -> ResponseCollectionSettings | None:
        result = await session.execute(
            sa.select(ResponseCollectionSettingsORM).where(ResponseCollectionSettingsORM.id == request.settings_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return model.to_domain()

    @override
    async def get_settings_by_vacancy(
        self, session: AsyncSession, request: ResponseCollectionRepositoryProtocol.GetSettingsByVacancyRequest
    ) -> ResponseCollectionSettings | None:
        result = await session.execute(
            sa
            .select(ResponseCollectionSettingsORM)
            .where(ResponseCollectionSettingsORM.vacancy_id == request.vacancy_id)
            .limit(1)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return model.to_domain()

    @override
    async def mark_candidate_processed(
        self, session: AsyncSession, request: ResponseCollectionRepositoryProtocol.MarkCandidateProcessedRequest
    ) -> ProcessedCandidate | None:
        stmt = (
            pg_insert(KnownCandidateORM)
            .values(
                resume_id=request.resume_id,
                vacancy_id=request.vacancy_id,
                source=request.source.value,
                source_id=request.source_id,
                created_at=sa.func.now(),
            )
            .on_conflict_do_nothing(index_elements=["resume_id", "vacancy_id"])
            .returning(KnownCandidateORM.id)
        )

        result = await session.execute(stmt)
        if result.scalar_one_or_none() is not None:
            return ProcessedCandidate(
                resume_id=request.resume_id,
                vacancy_id=request.vacancy_id,
            )
        return None

    @override
    async def is_candidate_processed(
        self, session: AsyncSession, request: ResponseCollectionRepositoryProtocol.IsCandidateProcessedRequest
    ) -> bool:
        vacancy_id_subq = (
            sa
            .select(ResponseCollectionSettingsORM.vacancy_id)
            .where(ResponseCollectionSettingsORM.id == request.settings_id)
            .scalar_subquery()
        )
        result = await session.scalar(
            sa.select(
                sa.exists(
                    sa
                    .select(1)
                    .select_from(KnownCandidateORM)
                    .where(
                        KnownCandidateORM.resume_id == request.resume_id,
                        KnownCandidateORM.vacancy_id == vacancy_id_subq,
                    )
                )
            )
        )
        return bool(result)

    @override
    async def update_settings_status(
        self, session: AsyncSession, request: ResponseCollectionRepositoryProtocol.UpdateSettingsStatusRequest
    ) -> None:
        _ = await session.execute(
            sa
            .update(ResponseCollectionSettingsORM)
            .where(ResponseCollectionSettingsORM.id == request.settings_id)
            .values(status=request.status)
        )
        await session.flush()
