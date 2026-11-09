from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import final, override

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.adapters.postgres_models.models import HharonUserORM
from hharon.domain.user import HharonUser
from hharon.infra.postgres import AsyncSessionFactory
from hharon.protocols.user.protocol import HharonUserRepositoryProtocol


@final
class PostgresHharonUserRepositoryAdapter(HharonUserRepositoryProtocol[AsyncSession]):
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
    async def create_user(
        self, session: AsyncSession, request: HharonUserRepositoryProtocol.CreateUserRequest
    ) -> HharonUser:
        model = HharonUserORM(
            user_id=request.user_id,
            hh_manager_id=request.hh_manager_id,
            hh_employer_id=request.hh_employer_id,
            name=request.name,
            email=request.email,
        )
        session.add(model)
        await session.flush()
        return model.to_domain()

    @override
    async def get_user(
        self, session: AsyncSession, request: HharonUserRepositoryProtocol.GetUserRequest
    ) -> HharonUser | None:
        result = await session.execute(sa.select(HharonUserORM).where(HharonUserORM.user_id == request.user_id))
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return model.to_domain()

    @override
    async def get_user_by_hh_manager_id(
        self, session: AsyncSession, request: HharonUserRepositoryProtocol.GetUserByHhIdRequest
    ) -> HharonUser | None:
        result = await session.execute(
            sa.select(HharonUserORM).where(HharonUserORM.hh_manager_id == request.hh_manager_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return model.to_domain()

    @override
    async def update_user(
        self, session: AsyncSession, request: HharonUserRepositoryProtocol.UpdateUserRequest
    ) -> HharonUser:
        result = await session.execute(
            sa.select(HharonUserORM).where(HharonUserORM.user_id == request.user_id).with_for_update()
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError("User not found")

        if request.name is not None:
            model.name = request.name
        if request.email is not None:
            model.email = request.email
        if request.hh_manager_id is not None:
            model.hh_manager_id = request.hh_manager_id
        if request.hh_employer_id is not None:
            model.hh_employer_id = request.hh_employer_id

        await session.flush()
        return model.to_domain()
