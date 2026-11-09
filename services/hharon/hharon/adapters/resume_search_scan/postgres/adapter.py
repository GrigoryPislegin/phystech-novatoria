import contextlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import final, override

import sqlalchemy as sa
from pydantic import TypeAdapter
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.adapters.postgres_models.models import KnownCandidateORM, SearchCampaignORM
from hharon.domain.known_candidate import KnownCandidateSourceEnum
from hharon.domain.resume_search_scan import ProcessedScanCandidate
from hharon.domain.search_campaign import SearchCampaign, SearchCampaignStatus
from hharon.infra.postgres import AsyncSessionFactory
from hharon.pkg import hhapi
from hharon.protocols.resume_search_scan import protocol


@final
class PostgresResumeSearchScanRepositoryAdapter(protocol.ResumeSearchScanRepositoryProtocol[AsyncSession]):
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
    async def create_campaign(
        self, session: AsyncSession, request: protocol.ResumeSearchScanRepositoryProtocol.CreateCampaignRequest
    ) -> SearchCampaign:
        param_adapter = TypeAdapter(list[hhapi.ResumesGetParameters])

        model = SearchCampaignORM(
            user_id=request.user_id,
            vacancy_id=request.vacancy_id,
            status=request.status,
            active_until=request.active_until,
            daily_limit=request.daily_limit,
            search_params=param_adapter.dump_python(
                request.search_params,
                exclude_unset=True,
                exclude_defaults=True,
                exclude_none=True,
            ),
        )
        session.add(model)
        await session.flush()
        return model.to_domain()

    @override
    async def update_campaign_status(
        self,
        session: AsyncSession,
        request: protocol.ResumeSearchScanRepositoryProtocol.UpdateCampaignStatusRequest,
    ) -> None:
        _ = await session.execute(
            sa
            .update(SearchCampaignORM)
            .where(
                SearchCampaignORM.id == request.campaign_id,
                SearchCampaignORM.deleted_at.is_(None),
            )
            .values(status=request.status)
        )

    @override
    async def get_campaign(
        self, session: AsyncSession, request: protocol.ResumeSearchScanRepositoryProtocol.GetCampaignRequest
    ) -> SearchCampaign | None:
        result = await session.execute(
            sa.select(SearchCampaignORM).where(
                SearchCampaignORM.id == request.campaign_id,
                SearchCampaignORM.deleted_at.is_(None),
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return model.to_domain()

    @override
    async def get_campaign_by_vacancy(
        self, session: AsyncSession, request: protocol.ResumeSearchScanRepositoryProtocol.GetCampaignByVacancyRequest
    ) -> SearchCampaign | None:
        # Return active campaign if exists, otherwise last non-active by created_at
        result = await session.execute(
            sa
            .select(SearchCampaignORM)
            .where(
                sa.and_(
                    SearchCampaignORM.vacancy_id == request.vacancy_id,
                    SearchCampaignORM.deleted_at.is_(None),
                )
            )
            .order_by(
                sa.case((SearchCampaignORM.status == SearchCampaignStatus.ACTIVE, 0), else_=1),
                SearchCampaignORM.created_at.desc(),
            )
            .limit(1)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return model.to_domain()

    @override
    async def delete_campaign(
        self, session: AsyncSession, request: protocol.ResumeSearchScanRepositoryProtocol.DeleteCampaignRequest
    ) -> None:
        result = await session.execute(
            sa
            .select(SearchCampaignORM)
            .where(
                SearchCampaignORM.id == request.campaign_id,
                SearchCampaignORM.deleted_at.is_(None),
            )
            .with_for_update(skip_locked=True)
        )
        model = result.scalar_one_or_none()

        if model is None:
            raise ValueError("Task not found")

        model.deleted_at = datetime.now(UTC)
        await session.flush()

    @override
    async def mark_candidate_processed(
        self,
        session: AsyncSession | None,
        request: protocol.ResumeSearchScanRepositoryProtocol.MarkCandidateProcessedRequest,
    ) -> ProcessedScanCandidate | None:
        async with contextlib.AsyncExitStack() as stack:
            if session:
                _ = await stack.enter_async_context(session.begin_nested())

            if session is None:
                session = await stack.enter_async_context(self.context())

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
                return ProcessedScanCandidate(
                    resume_id=request.resume_id,
                    vacancy_id=request.vacancy_id,
                )
            return None

    @override
    async def count_collected_by_date(
        self,
        session: AsyncSession,
        request: protocol.ResumeSearchScanRepositoryProtocol.CountCollectedTodayRequest,
    ) -> protocol.ResumeSearchScanRepositoryProtocol.CountCollectedTodayResponse:
        campaign_vacancy = (
            sa
            .select(SearchCampaignORM.vacancy_id)
            .where(
                SearchCampaignORM.id == request.campaign_id,
                SearchCampaignORM.deleted_at.is_(None),
            )
            .scalar_subquery()
        )
        result = await session.execute(
            sa.select(func.count(KnownCandidateORM.id)).where(
                KnownCandidateORM.vacancy_id == campaign_vacancy,
                KnownCandidateORM.source == KnownCandidateSourceEnum.SEARCH_CAMPAIGN.value,
                KnownCandidateORM.source_id == request.campaign_id,
                func.date(KnownCandidateORM.created_at) == request.date,
            )
        )
        count = result.scalar()
        return protocol.ResumeSearchScanRepositoryProtocol.CountCollectedTodayResponse(
            collected_current=count if count is not None else 0
        )
