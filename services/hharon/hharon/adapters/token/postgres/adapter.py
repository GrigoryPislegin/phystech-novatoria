from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import final, override

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.adapters.postgres_models.models import HeadHunterTokenORM
from hharon.domain.token import TokenPair
from hharon.infra.postgres import AsyncSessionFactory
from hharon.protocols.token.protocol import (
    HeadHunterTokenRepositoryNotFoundError,
    HeadHunterTokenRepositoryProtocol,
)


@final
class PostgresHeadHunterTokenRepositoryAdapter(HeadHunterTokenRepositoryProtocol[AsyncSession]):
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
    async def save_tokens(
        self, session: AsyncSession, request: HeadHunterTokenRepositoryProtocol.SaveTokensRequest
    ) -> TokenPair:
        model = HeadHunterTokenORM(
            user_id=request.user_id,
            encrypted_access_token=request.encrypted_access_token,
            encrypted_refresh_token=request.encrypted_refresh_token,
            expires_at=request.expires_at,
            token_type=request.token_type,
        )
        session.add(model)
        await session.flush()
        return model.to_domain()

    @override
    async def get_tokens(
        self, session: AsyncSession, request: HeadHunterTokenRepositoryProtocol.GetTokensRequest
    ) -> TokenPair | None:
        result = await session.execute(
            sa.select(HeadHunterTokenORM).where(HeadHunterTokenORM.user_id == request.user_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return model.to_domain()

    @override
    async def lock_tokens_for_update(
        self, session: AsyncSession, request: HeadHunterTokenRepositoryProtocol.LockTokensRequest
    ) -> TokenPair | None:
        result = await session.execute(
            sa.select(HeadHunterTokenORM).where(HeadHunterTokenORM.user_id == request.user_id).with_for_update()
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return model.to_domain()

    @override
    async def update_tokens(
        self, session: AsyncSession, request: HeadHunterTokenRepositoryProtocol.UpdateTokensRequest
    ) -> TokenPair:
        result = await session.execute(
            sa.select(HeadHunterTokenORM).where(HeadHunterTokenORM.user_id == request.user_id).with_for_update()
        )
        model = result.scalar_one_or_none()
        if model is None:
            error_msg = f"Token pair not found for user_id: {request.user_id}"
            raise HeadHunterTokenRepositoryNotFoundError(error_msg)

        model.encrypted_access_token = request.encrypted_access_token
        model.encrypted_refresh_token = request.encrypted_refresh_token
        model.expires_at = request.expires_at
        model.token_type = request.token_type
        if request.is_invalid is not None:
            model.is_invalid = request.is_invalid

        await session.flush()
        return model.to_domain()

    @override
    async def mark_tokens_invalid(
        self, session: AsyncSession, request: HeadHunterTokenRepositoryProtocol.MarkTokensInvalidRequest
    ) -> TokenPair:
        result = await session.execute(
            sa.select(HeadHunterTokenORM).where(HeadHunterTokenORM.user_id == request.user_id).with_for_update()
        )
        model = result.scalar_one_or_none()
        if model is None:
            error_msg = f"Token pair not found for user_id: {request.user_id}"
            raise HeadHunterTokenRepositoryNotFoundError(error_msg)

        model.is_invalid = True
        await session.flush()
        return model.to_domain()
